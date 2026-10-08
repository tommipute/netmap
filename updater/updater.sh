#!/usr/bin/env bash
# Aggiornamenti automatici di NetMap. Gira sull'HOST (fuori dai container), lanciato ogni minuto dal timer
# systemd o da cron (vedi install.sh). L'app non si aggiorna da sola: scrive le richieste e le impostazioni nella
# cartella condivisa e legge lo stato che scrive questo script.
#
#   updater-data/settings.json  impostazioni (scritte dall'app): auto_update, branch (o canale), intervallo, backup
#                               da tenere, backup notturno (sì/no, ora, giorni da tenere)
#   updater-data/request.json   richiesta dall'app ("check", "update" o "backup"): letta e svuotata qui
#   updater-data/status.json    stato per l'app: versioni, ultimo controllo, attività in corso, storico, backup
#   updater-data/updater.log    log dell'ultimo aggiornamento (più le righe dei controlli successivi)
#
# Uso:  updater.sh               un giro normale (quello del timer)
#       updater.sh version-env   riscrive solo version.env con il commit installato
#       updater.sh restore FILE  ripristina un backup del database (app ferma durante il ripristino)
#
# Modalità (updater.conf): docker = repo git + docker compose build (sviluppo, server con il codice sorgente),
# vm = repo git senza Docker, image = installazione con deploy/install.sh: immagini già pronte dal registro, canale
# stable/beta, versione in .env (NETMAP_VERSION); compose, Caddyfile e questo script arrivano dall'immagine nuova.
#
# Tutto il codice è dentro funzioni e l'ultima riga chiama main ed esce: bash legge l'intero file prima di
# eseguirlo, così il git pull che riscrive questo script durante l'aggiornamento non lo rompe.

set -uo pipefail

# ------------------------------------------------------------------------------------------- configurazione
load_config() {
  SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  CONF=${NETMAP_UPDATER_CONF:-$SCRIPT_DIR/updater.conf}
  # shellcheck disable=SC1090
  [ -f "$CONF" ] && . "$CONF"
  MODE=${MODE:-docker}
  APP_DIR=${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}
  DATA_DIR=${DATA_DIR:-$APP_DIR/updater-data}
  BACKUP_DIR=${BACKUP_DIR:-$APP_DIR/backups}
  REMOTE=${REMOTE:-origin}
  HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:8001/api/health}
  WEB_URL=${WEB_URL-http://127.0.0.1:5174/}
  HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}
  HEALTH_INTERVAL=${HEALTH_INTERVAL:-5}
  # Modalità vm: comandi del server senza Docker (vedi updater.conf.example)
  VM_DEPLOY_CMD=${VM_DEPLOY_CMD:-}
  VM_STOP_CMD=${VM_STOP_CMD:-}
  VM_DATABASE_URL=${VM_DATABASE_URL:-}
  if [ -n "${GIT_SSH_KEY:-}" ]; then
    export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes"
  fi
  export GIT_TERMINAL_PROMPT=0
  # Modalità image: registro e versione installata stanno nel .env dell'installazione
  ENV_FILE=$APP_DIR/.env
  if [ "$MODE" = image ]; then
    IMAGE=$(env_get NETMAP_IMAGE)
    IMAGE=${IMAGE:-ghcr.io/tommipute/netmap}
  fi
  STATUS=$DATA_DIR/status.json
  SETTINGS=$DATA_DIR/settings.json
  REQUEST=$DATA_DIR/request.json
  LOG=$DATA_DIR/updater.log
  umask 002
}

# ------------------------------------------------------------------------------------------------- utilità
now() { date -Iseconds; }

log() {
  local line
  line="$(date '+%F %T') $*"
  echo "$line"
  echo "$line" >>"$LOG"
}

die() { log "ERRORE: $*"; exit 1; }

# Scrittura atomica: l'app non legge mai un file a metà
write_json() { # file, contenuto
  local tmp
  tmp=$(mktemp "$1.XXXXXX") || return 1
  printf '%s\n' "$2" >"$tmp" && chmod 664 "$tmp" && mv -f "$tmp" "$1"
}

# Modifica status.json con un filtro jq: status '.campo = $v' --arg v valore
status() {
  local filter=$1
  shift
  local out
  out=$(jq "$@" "$filter" "$STATUS") || { echo "jq non riesce ad aggiornare lo stato ($filter)" >&2; return 1; }
  write_json "$STATUS" "$out"
}

setting() { # chiave, valore predefinito
  local value
  value=$(jq -r --arg k "$1" 'if .[$k] == null then empty else .[$k] end' "$SETTINGS" 2>/dev/null)
  echo "${value:-$2}"
}

# Valori del file .env (modalità image)
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | tail -n1 | sed "s/^[\"']//; s/[\"']\$//"; }

env_set() { # chiave, valore: copia con gli stessi permessi (il .env contiene la password del database)
  cp -p "$ENV_FILE" "$ENV_FILE.tmp" &&
    if grep -q "^$1=" "$ENV_FILE.tmp"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE.tmp"; else echo "$1=$2" >>"$ENV_FILE.tmp"; fi &&
    mv -f "$ENV_FILE.tmp" "$ENV_FILE"
}

# Versione di un'immagine (modalità image), dalle etichette scritte al build: stesso JSON di commit_info
image_info() { # tag dell'immagine
  local labels
  labels=$(docker image inspect --format '{{json .Config.Labels}}' "$IMAGE-backend:$1" 2>/dev/null) || return 1
  jq -e '(.["org.opencontainers.image.revision"] // "") as $c | select($c != "")
    | {commit: $c, short: $c[0:7], date: (.["io.netmap.commit-date"] // ""), version: (.["org.opencontainers.image.version"] // ""),
       tag: ("v" + (.["org.opencontainers.image.version"] // "")), subject: ""}' <<<"$labels"
}

# true se la versione $1 è più nuova di $2 (semver: 1.2.0 > 1.2.0-rc.2 > 1.2.0-rc.1 > 1.1.9)
version_gt() {
  jq -n -e --arg a "$1" --arg b "$2" '
    def key: ltrimstr("v") | (index("-") // length) as $i | .[:$i] as $main | .[$i + 1:] as $pre
      | [($main | split(".") | map(tonumber? // 0)), (if $pre == "" then [1] else [0, ($pre | split(".") | map(tonumber? // .))] end)];
    ($a | key) > ($b | key)' >/dev/null
}

# Copia nella cartella dell'installazione i file che viaggiano dentro l'immagine (/app/deploy): docker-compose.yml,
# Caddyfile, env.example, install.sh e updater/ (compreso questo script, riscritto senza danni: vedi sopra)
deploy_files() { # tag
  docker run --rm --entrypoint tar "$IMAGE-backend:$1" -C /app/deploy -cf - . | tar -xf - -C "$APP_DIR" --no-same-owner
}

# Versione di un commit: hash, data, tag e numero di version.js, come JSON
commit_info() {
  local ref=$1 commit date tag version subject
  commit=$(git rev-parse --verify -q "$ref^{commit}") || return 1
  date=$(git show -s --format=%cI "$commit")
  subject=$(git show -s --format=%s "$commit")
  tag=$(git describe --tags --exact-match "$commit" 2>/dev/null || git describe --tags --abbrev=0 "$commit" 2>/dev/null || true)
  # L'ultima stringa tra virgolette della riga di VERSION (anche "VITE_APP_VERSION || '2026.10.08-5'")
  version=$(git show "$commit:frontend/src/version.js" 2>/dev/null | sed -n "/VERSION *=/s/.*['\"]\([^'\"]*\)['\"].*/\1/p" | head -n1)
  jq -n --arg commit "$commit" --arg date "$date" --arg tag "$tag" --arg version "$version" --arg subject "$subject" \
    '{commit: $commit, short: $commit[0:7], date: $date, tag: $tag, version: $version, subject: $subject}'
}

# Il commit installato arriva all'app come variabili d'ambiente (compose: env_file version.env)
write_version_env() {
  [ "$MODE" = image ] && return 0 # la versione è scritta dentro le immagini
  local info
  info=$(commit_info HEAD) || return 1
  jq -r '"# Scritto da updater/updater.sh: versione installata, letta dall'"'"'app all'"'"'avvio\n" +
    "APP_COMMIT=\(.commit)\nAPP_COMMIT_DATE=\(.date)\nAPP_TAG=\(.tag)\nAPP_VERSION=\(.version)"' <<<"$info" >"$APP_DIR/version.env.tmp" &&
    mv -f "$APP_DIR/version.env.tmp" "$APP_DIR/version.env"
}

# ------------------------------------------------------------------------------- database, avvio, health
compose() { docker compose --project-directory "$APP_DIR" "$@"; }

db_revision() {
  if [ "$MODE" != vm ]; then
    compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' 2>/dev/null | tr -d '[:space:]'
  else
    psql "$VM_DATABASE_URL" -tAc "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]'
  fi
}

db_backup() { # file
  if [ "$MODE" != vm ]; then
    compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$1"
  else
    pg_dump "$VM_DATABASE_URL" -Fc >"$1"
  fi
}

# Svuota lo schema e ricarica il backup: le tabelle create dalle migration nuove spariscono del tutto
db_restore() { # file
  local reset='DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
  if [ "$MODE" != vm ]; then
    compose exec -T db sh -c "psql -v ON_ERROR_STOP=1 -q -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c '$reset'" &&
      compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' <"$1"
  else
    psql "$VM_DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "$reset" &&
      pg_restore -d "$VM_DATABASE_URL" --no-owner --exit-on-error <"$1"
  fi
}

app_stop() {
  if [ "$MODE" != vm ]; then
    compose stop api worker monitor web
  else
    bash -c "$VM_STOP_CMD"
  fi
}

app_deploy() {
  if [ "$MODE" = docker ]; then
    # version.env cambia a ogni aggiornamento: compose ricrea i container dell'app (api applica le migration)
    compose up -d --build
  elif [ "$MODE" = image ]; then
    compose up -d --remove-orphans # le immagini sono già scaricate
  else
    (cd "$APP_DIR" && bash -c "$VM_DEPLOY_CMD")
  fi
}

# L'API deve rispondere "ok" con il commit atteso (non quello vecchio ancora acceso); poi anche l'interfaccia
# Modalità image: API e interfaccia non hanno porte sull'host, si interrogano da dentro i loro container
fetch_health() {
  if [ "$MODE" = image ]; then
    compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read().decode())" 2>/dev/null
  else
    curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null
  fi
}

web_ok() {
  if [ "$MODE" = image ]; then
    compose exec -T web wget -q -T 5 -O /dev/null http://127.0.0.1/ 2>/dev/null
  else
    [ -z "$WEB_URL" ] || curl -fsS --max-time 5 -o /dev/null "$WEB_URL" 2>/dev/null
  fi
}

health_check() { # commit atteso
  local expected=$1 deadline body status commit
  deadline=$(($(date +%s) + HEALTH_TIMEOUT))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    body=$(fetch_health) || body=
    status=$(jq -r '.status // empty' <<<"$body" 2>/dev/null)
    commit=$(jq -r '.commit // empty' <<<"$body" 2>/dev/null)
    if [ "$status" = ok ] && [ "$commit" = "$expected" ]; then
      if web_ok; then
        log "Health check superato (commit ${expected:0:7})"
        return 0
      fi
    fi
    sleep "$HEALTH_INTERVAL"
  done
  log "Health check fallito dopo ${HEALTH_TIMEOUT}s: ultima risposta ${body:-nessuna}"
  return 1
}

# --------------------------------------------------------------------------------------------- aggiornamento
step() { # attività, messaggio
  log "$2"
  status '.activity = $a | .activity_message = $m | .activity_since = (if .activity == $a then .activity_since else $t end)' \
    --arg a "$1" --arg m "$2" --arg t "$(now)" || true
}

finish() { # esito, messaggio, ripristino db (true/false)
  local outcome=$1 message=$2 restored=${3:-false} entry
  log "Esito: $outcome. $message"
  entry=$(jq -n --arg started "$STARTED" --arg finished "$(now)" --arg trigger "$TRIGGER" --arg by "$REQUESTED_BY" \
    --argjson from "$FROM" --argjson to "$TO" --arg outcome "$outcome" --arg message "$message" \
    --arg backup "${BACKUP_FILE##*/}" --argjson restored "$restored" \
    '{started_at: $started, finished_at: $finished, trigger: $trigger, requested_by: $by, from: $from, to: $to,
      outcome: $outcome, message: $message, backup: $backup, db_restored: $restored}')
  status '.activity = "idle" | .activity_message = "" | .activity_since = null
    | .last_result = {outcome: $e.outcome, message: $e.message, at: $e.finished_at}
    | .history = ([$e] + (.history // []))[0:20]' --argjson e "$entry"
}

rollback() { # motivo
  local reason=$1 restored=false
  step rolling_back "Ripristino la versione precedente (${PREV_COMMIT:0:7}): $reason"
  app_stop >>"$LOG" 2>&1 || log "Attenzione: non riesco a fermare l'app"
  if [ "$MODE" = image ]; then
    env_set NETMAP_VERSION "$PREV_VERSION" && deploy_files "$PREV_VERSION" >>"$LOG" 2>&1
  elif [ -n "$PREV_BRANCH" ]; then
    git checkout -q -f -B "$PREV_BRANCH" "$PREV_COMMIT" >>"$LOG" 2>&1
  else
    git checkout -q -f --detach "$PREV_COMMIT" >>"$LOG" 2>&1
  fi || {
    finish error "Rollback fallito: non riesco a tornare alla versione ${PREV_COMMIT:0:7}. $reason"
    return 1
  }
  if [ "$(db_revision)" != "$DB_REV_BEFORE" ]; then
    log "Le migration hanno cambiato il database ($DB_REV_BEFORE → $(db_revision)): ripristino il backup ${BACKUP_FILE##*/}"
    if db_restore "$BACKUP_FILE" >>"$LOG" 2>&1; then
      restored=true
    else
      finish error "Rollback fallito: il ripristino del backup ${BACKUP_FILE##*/} non è riuscito. $reason" false
      return 1
    fi
  else
    log "Database non toccato dalle migration: nessun ripristino necessario"
  fi
  write_version_env
  app_deploy >>"$LOG" 2>&1 || log "Attenzione: il riavvio della versione precedente ha dato errori"
  status '.failed_commit = $c' --arg c "$(jq -r .commit <<<"$TO")"
  if health_check "$PREV_COMMIT"; then
    status '.installed = $i' --argjson i "$FROM"
    finish rolled_back "$reason Ripristinata la versione ${PREV_COMMIT:0:7}." "$restored"
  else
    finish error "$reason Anche la versione precedente non risponde: serve un intervento manuale (vedi README)." "$restored"
  fi
}

do_update() {
  STARTED=$(now)
  BACKUP_FILE=
  if [ "$MODE" = image ]; then
    PREV_VERSION=$(env_get NETMAP_VERSION)
    FROM=$INSTALLED
    PREV_COMMIT=$(jq -r .commit <<<"$FROM")
  else
    PREV_COMMIT=$(git rev-parse HEAD)
    PREV_BRANCH=$(git symbolic-ref --short -q HEAD || true)
    FROM=$(commit_info HEAD)
  fi
  : >"$LOG"
  step updating "Aggiornamento ${PREV_COMMIT:0:7} → $(jq -r .short <<<"$TO") ($TRIGGER${REQUESTED_BY:+, $REQUESTED_BY})"

  if [ "$MODE" = image ]; then
    # Prima di toccare qualsiasi cosa: se il download non riesce, resta tutto com'è
    step updating "Scarico la versione nuova"
    local new
    new=$(jq -r .version <<<"$TO")
    if ! { docker pull -q "$IMAGE-backend:$new" && docker pull -q "$IMAGE-web:$new"; } >>"$LOG" 2>&1; then
      finish error "Download della versione nuova non riuscito: aggiornamento annullato, nulla è cambiato."
      return 1
    fi
  elif [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    finish error "Nella cartella dell'app ci sono file modificati a mano: aggiornamento annullato, nulla è cambiato. $(git status --porcelain --untracked-files=no | head -5 | tr '\n' ' ')"
    return 1
  fi

  step updating "Backup del database"
  DB_REV_BEFORE=$(db_revision)
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE=$BACKUP_DIR/netmap-$(date +%Y%m%d-%H%M%S)-${PREV_COMMIT:0:7}.dump
  if ! db_backup "$BACKUP_FILE" 2>>"$LOG" || [ ! -s "$BACKUP_FILE" ]; then
    rm -f "$BACKUP_FILE"
    BACKUP_FILE=
    finish error "Backup del database non riuscito: aggiornamento annullato, nulla è cambiato."
    return 1
  fi
  log "Backup: ${BACKUP_FILE##*/} ($(du -h "$BACKUP_FILE" | cut -f1)), migration del database: ${DB_REV_BEFORE:-nessuna}"
  # Tengo solo gli ultimi N backup
  find "$BACKUP_DIR" -maxdepth 1 -name 'netmap-*.dump' -printf '%T@ %p\n' | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- |
    while read -r old; do rm -f -- "$old" && log "Backup vecchio eliminato: ${old##*/}"; done

  echo "$PREV_COMMIT" >"$DATA_DIR/previous_commit"
  status '.previous = $p' --argjson p "$FROM"

  if [ "$MODE" = image ]; then
    echo "$PREV_VERSION" >"$DATA_DIR/previous_version"
    if ! { deploy_files "$new" && env_set NETMAP_VERSION "$new" && compose pull -q --ignore-pull-failures; } >>"$LOG" 2>&1; then
      rollback "I file della versione nuova non si installano."
      return 1
    fi
  else
    step updating "Scarico il codice nuovo (branch $BRANCH)"
    # Equivale a git pull, ma funziona anche cambiando branch o dopo un force push
    if ! git checkout -q -B "$BRANCH" "$REMOTE/$BRANCH" >>"$LOG" 2>&1; then
      rollback "git non riesce a passare al codice nuovo."
      return 1
    fi
    write_version_env
  fi

  step updating "Ricostruisco e riavvio l'app"
  if ! app_deploy >>"$LOG" 2>&1; then
    rollback "Il riavvio dell'app con il codice nuovo non è riuscito."
    return 1
  fi
  step updating "Controllo che l'app risponda"
  if ! health_check "$(jq -r .commit <<<"$TO")"; then
    rollback "La versione nuova non risponde al controllo di salute."
    return 1
  fi
  status '.installed = $i | .update_available = false | .failed_commit = null' --argjson i "$TO"
  finish success "Installata la versione $(jq -r '.version // empty' <<<"$TO") ($(jq -r .short <<<"$TO"))."
}

# ---------------------------------------------------------------------------------------------- backup
# Backup notturno (daily-*.dump, tenuti BACKUP_KEEP_DAYS giorni) e a richiesta dall'app (manual-*.dump, stessa
# durata); quelli fatti prima di ogni aggiornamento (netmap-*.dump) seguono keep_backups.
backup_now() { # tipo: daily | manual
  local kind=$1 file
  file=$BACKUP_DIR/$kind-$(date +%Y%m%d-%H%M%S).dump
  mkdir -p "$BACKUP_DIR"
  status '.activity = "backup" | .activity_message = "Backup del database" | .activity_since = $t' --arg t "$(now)"
  if db_backup "$file" 2>>"$LOG" && [ -s "$file" ]; then
    log "Backup ${kind}: ${file##*/} ($(du -h "$file" | cut -f1))"
    status '.backup.last = {at: $t, kind: $k, ok: true, file: $f, message: ""}' --arg t "$(now)" --arg k "$kind" --arg f "${file##*/}"
  else
    rm -f "$file"
    log "Backup $kind non riuscito"
    status '.backup.last = {at: $t, kind: $k, ok: false, file: "", message: "Backup del database non riuscito: guarda il log."}' \
      --arg t "$(now)" --arg k "$kind"
  fi
  status '.activity = "idle" | .activity_message = "" | .activity_since = null'
}

run_backups() {
  # Notturno: una volta al giorno, dopo l'ora scelta (se il server era spento a quell'ora, appena si riaccende).
  # Il giorno si segna anche se il backup fallisce, così non si riprova ogni minuto: l'errore resta visibile nell'app.
  local today hhmm
  today=$(date +%F)
  hhmm=$(date +%H:%M)
  if [ "$BACKUP_DAILY" = true ] && [[ ! $hhmm < $BACKUP_TIME ]] && [ "$(jq -r '.backup.last_daily_date // empty' "$STATUS")" != "$today" ]; then
    status '.backup.last_daily_date = $d' --arg d "$today"
    backup_now daily
  fi
  [ "$ACTION" = backup ] && backup_now manual
  # Pulizia dei vecchi notturni e manuali
  find "$BACKUP_DIR" -maxdepth 1 \( -name 'daily-*.dump' -o -name 'manual-*.dump' \) -mmin +$((BACKUP_KEEP_DAYS * 1440)) -print 2>/dev/null |
    while read -r old; do rm -f -- "$old" && log "Backup vecchio eliminato: ${old##*/}"; done
  # Elenco per l'app (i 100 più recenti)
  local list
  list=$(find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' -printf '%T@\t%s\t%f\n' 2>/dev/null | sort -rn | head -n 100 |
    jq -R -s '[split("\n")[] | select(length > 0) | split("\t") | {
      date: (.[0] | tonumber | floor | todate), size: (.[1] | tonumber), file: .[2],
      kind: (if (.[2] | startswith("daily-")) then "daily" elif (.[2] | startswith("manual-")) then "manual" else "update" end)}]')
  status '.backup.files = $l | .backup.dir = $d' --argjson l "${list:-[]}" --arg d "$BACKUP_DIR"
}

# ------------------------------------------------------------------------------------------------- giro
run() {
  mkdir -p "$DATA_DIR" || exit 1
  exec 9>"$DATA_DIR/.updater.lock"
  flock -n 9 || exit 0 # c'è già un giro in corso (es. un aggiornamento lungo)
  cd "$APP_DIR" || die "Cartella dell'app non trovata: $APP_DIR"
  [ -s "$STATUS" ] && jq -e . "$STATUS" >/dev/null 2>&1 || write_json "$STATUS" '{"history": []}'
  # Il log non cresce all'infinito: dopo 1 MB riparte da capo
  [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1048576 ] && : >"$LOG"

  AUTO=$(setting auto_update false)
  BRANCH=$(setting branch main)
  CHANNEL=$(setting channel stable)
  [ "$CHANNEL" = stable ] || [ "$CHANNEL" = beta ] || CHANNEL=stable
  INTERVAL=$(setting check_interval_minutes 60)
  KEEP=$(setting keep_backups 10)
  [[ $INTERVAL =~ ^[0-9]+$ ]] && [ "$INTERVAL" -ge 1 ] || INTERVAL=60
  [[ $KEEP =~ ^[0-9]+$ ]] && [ "$KEEP" -ge 1 ] || KEEP=10
  BACKUP_DAILY=$(setting backup_daily true)
  BACKUP_TIME=$(setting backup_time 02:30)
  BACKUP_KEEP_DAYS=$(setting backup_keep_days 14)
  [[ $BACKUP_TIME =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || BACKUP_TIME=02:30
  [[ $BACKUP_KEEP_DAYS =~ ^[0-9]+$ ]] && [ "$BACKUP_KEEP_DAYS" -ge 1 ] || BACKUP_KEEP_DAYS=14

  # La richiesta dell'app si legge e si svuota subito, anche se poi qualcosa va storto
  ACTION=$(jq -r '.action // empty' "$REQUEST" 2>/dev/null)
  REQUESTED_BY=$(jq -r '.requested_by // empty' "$REQUEST" 2>/dev/null)
  [ -n "$ACTION" ] && write_json "$REQUEST" '{}'
  case $ACTION in check | update | backup | '') ;; *) log "Richiesta sconosciuta ignorata: $ACTION"; ACTION= ;; esac

  status '.updater = {mode: $mode, app_dir: $dir} | .last_run = $t | .activity = (.activity // "idle")
    | .settings = {auto_update: ($auto == "true"), branch: $branch, channel: $channel, check_interval_minutes: ($int | tonumber), keep_backups: ($keep | tonumber),
                   backup_daily: ($daily == "true"), backup_time: $time, backup_keep_days: ($days | tonumber)}' \
    --arg mode "$MODE" --arg dir "$APP_DIR" --arg t "$(now)" --arg auto "$AUTO" --arg branch "$BRANCH" --arg channel "$CHANNEL" \
    --arg int "$INTERVAL" --arg keep "$KEEP" --arg daily "$BACKUP_DAILY" --arg time "$BACKUP_TIME" --arg days "$BACKUP_KEEP_DAYS" || exit 1
  # Un giro precedente interrotto a metà (es. riavvio dell'host) non deve lasciare "in corso" per sempre
  status '.activity = "idle"'
  if [ "$MODE" = image ]; then
    local version
    version=$(env_get NETMAP_VERSION)
    INSTALLED=$(image_info "$version" || jq -n --arg v "$version" '{commit: "", short: "", date: "", version: $v, tag: ("v" + $v), subject: ""}')
  else
    INSTALLED=$(commit_info HEAD)
  fi
  [ -n "$INSTALLED" ] && status '.installed = $i' --argjson i "$INSTALLED"
  run_backups

  if [ "$MODE" != image ] && ! git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || [[ $BRANCH == -* ]]; then
    status '.check_error = $e | .last_check = $t' --arg e "Branch non valido: $BRANCH" --arg t "$(now)"
    die "Branch non valido nelle impostazioni: $BRANCH"
  fi

  # Controllo solo se l'app lo chiede o se è passato l'intervallo
  local last due=false
  last=$(jq -r '.last_check // empty' "$STATUS")
  if [ "$ACTION" = check ] || [ "$ACTION" = update ] || [ -z "$last" ]; then
    due=true
  elif [ $(($(date +%s) - $(date -d "$last" +%s 2>/dev/null || echo 0))) -ge $((INTERVAL * 60)) ]; then
    due=true
  fi
  $due || exit 0

  status '.activity = "checking" | .activity_message = "Controllo se ci sono aggiornamenti" | .activity_since = $t' --arg t "$(now)"
  [ "$MODE" = image ] && { check_image; return; }
  local fetch_out
  if ! fetch_out=$(git fetch --quiet --prune "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH" 2>&1); then
    status '.activity = "idle" | .last_check = $t | .check_error = $e' --arg t "$(now)" \
      --arg e "git fetch non riuscito: ${fetch_out:-errore sconosciuto}"
    log "Controllo non riuscito: $fetch_out"
    exit 1
  fi
  TO=$(commit_info "$REMOTE/$BRANCH")
  local local_commit remote_commit available=false
  local_commit=$(git rev-parse HEAD)
  remote_commit=$(jq -r .commit <<<"$TO")
  [ "$local_commit" != "$remote_commit" ] && available=true
  status '.activity = "idle" | .activity_message = "" | .activity_since = null | .last_check = $t | .check_error = null
    | .available = $to | .update_available = $av' --arg t "$(now)" --argjson to "$TO" --argjson av "$available"
  log "Controllo: installato ${local_commit:0:7}, disponibile ${remote_commit:0:7} su $BRANCH${ACTION:+ (richiesta: $ACTION)}"

  $available || exit 0
  decide_update "$remote_commit"
}

# Aggiorna se l'ha chiesto l'app, oppure in automatico se il commit non è già fallito una volta
decide_update() { # commit disponibile
  local remote_commit=$1 failed
  failed=$(jq -r '.failed_commit // empty' "$STATUS")
  if [ "$ACTION" = update ]; then
    TRIGGER=manual
  elif [ "$AUTO" = true ] && [ "$remote_commit" != "$failed" ]; then
    TRIGGER=auto
  else
    [ "$AUTO" = true ] && log "Aggiornamento automatico saltato: il commit ${remote_commit:0:7} è già fallito una volta (si può forzare dall'app)"
    exit 0
  fi
  do_update
}

# Modalità image: l'ultima versione del canale è l'immagine con tag stable (o beta); la si scarica (se non è cambiata
# docker scarica solo l'indice) e si leggono le etichette. Si aggiorna solo verso versioni più nuove.
check_image() {
  local out installed_version available=false
  if ! out=$(docker pull -q "$IMAGE-backend:$CHANNEL" 2>&1) || ! TO=$(image_info "$CHANNEL"); then
    status '.activity = "idle" | .activity_message = "" | .activity_since = null | .last_check = $t | .check_error = $e' --arg t "$(now)" \
      --arg e "Download dal registro non riuscito: ${out:-etichette della versione mancanti}"
    log "Controllo non riuscito: $out"
    exit 1
  fi
  installed_version=$(jq -r .version <<<"$INSTALLED")
  version_gt "$(jq -r .version <<<"$TO")" "$installed_version" && available=true
  status '.activity = "idle" | .activity_message = "" | .activity_since = null | .last_check = $t | .check_error = null
    | .available = $to | .update_available = $av' --arg t "$(now)" --argjson to "$TO" --argjson av "$available"
  log "Controllo: installata $installed_version, disponibile $(jq -r .version <<<"$TO") sul canale $CHANNEL${ACTION:+ (richiesta: $ACTION)}"
  $available || exit 0
  decide_update "$(jq -r .commit <<<"$TO")"
}

main() {
  load_config
  command -v jq >/dev/null || { echo "Manca jq: installalo (apt install jq)" >&2; exit 1; }
  case ${1:-run} in
    run) run ;;
    version-env)
      [ "$MODE" = image ] && { echo "Modalità image: la versione è dentro le immagini, version.env non serve"; exit 0; }
      cd "$APP_DIR" && write_version_env && echo "Scritto $APP_DIR/version.env" ;;
    restore)
      [ -f "${2:-}" ] || { echo "Uso: $0 restore FILE.dump" >&2; exit 1; }
      cd "$APP_DIR" || exit 1
      mkdir -p "$DATA_DIR" && exec 9>"$DATA_DIR/.updater.lock" && flock -n 9 || { echo "C'è un aggiornamento in corso: riprova dopo" >&2; exit 1; }
      LOG=/dev/null
      app_stop && db_restore "$2" && app_deploy && echo "Backup ripristinato: $2"
      ;;
    *) echo "Uso: $0 [run|version-env|restore FILE]" >&2; exit 1 ;;
  esac
}

main "$@"; exit $?
