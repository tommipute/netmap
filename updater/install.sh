#!/usr/bin/env bash
# Installa l'updater di NetMap sull'host: configurazione, cartella condivisa con l'app, timer systemd (o cron).
#
#   sudo updater/install.sh              modalità docker (consigliata)
#   sudo updater/install.sh --mode vm    app installata direttamente sul server, senza Docker
#   sudo updater/install.sh --mode image installazione con immagini pronte (la usa deploy/install.sh)
#   sudo updater/install.sh --uninstall  toglie timer/cron (cartelle, backup e configurazione restano)
#
# Lo script gira con l'utente che ha lanciato sudo: deve poter usare git (deploy key) e docker.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
RUN_USER=${SUDO_USER:-$(id -un)}
RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
MODE=docker
UNINSTALL=false
UNIT=netmap-updater

while [ $# -gt 0 ]; do
  case $1 in
    --mode) MODE=${2:-}; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    -h | --help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $1" >&2; exit 1 ;;
  esac
done
[[ $MODE =~ ^(docker|vm|image)$ ]] || { echo "--mode deve essere docker, vm o image" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Lancialo con sudo: sudo $0 $*" >&2; exit 1; }
[ "$RUN_USER" != root ] || echo "Attenzione: l'updater girerà come root. Meglio lanciare sudo da un utente normale."

as_user() { sudo -u "$RUN_USER" -H "$@"; }
has_systemd() { [ -d /run/systemd/system ] && command -v systemctl >/dev/null; }

if $UNINSTALL; then
  if has_systemd; then
    systemctl disable --now "$UNIT.timer" 2>/dev/null || true
    rm -f "/etc/systemd/system/$UNIT.service" "/etc/systemd/system/$UNIT.timer"
    systemctl daemon-reload
  fi
  rm -f "/etc/cron.d/$UNIT"
  echo "Updater disinstallato. Restano updater/updater.conf, updater-data/ e backups/."
  exit 0
fi

echo "== NetMap updater: modalità $MODE, cartella $APP_DIR, utente $RUN_USER"

# ---------------------------------------------------------------------------------------- programmi
missing=()
for cmd in jq curl flock sudo $([ "$MODE" = image ] || echo git); do command -v "$cmd" >/dev/null || missing+=("$cmd"); done
[ ${#missing[@]} -eq 0 ] || { echo "Mancano: ${missing[*]}. Installa con: sudo apt install ${missing[*]}" >&2; exit 1; }
if [ "$MODE" != vm ]; then
  docker compose version >/dev/null 2>&1 || { echo "Manca docker compose (plugin v2)" >&2; exit 1; }
  if [ "$RUN_USER" != root ] && ! id -nG "$RUN_USER" | grep -qw docker; then
    echo "L'utente $RUN_USER non è nel gruppo docker: sudo usermod -aG docker $RUN_USER (poi riesci e rientra)" >&2
    exit 1
  fi
else
  for cmd in psql pg_dump pg_restore; do command -v "$cmd" >/dev/null || { echo "Manca $cmd (postgresql-client)" >&2; exit 1; }; done
fi

# ---------------------------------------------------------------------------------------- configurazione
CONF=$SCRIPT_DIR/updater.conf
if [ ! -f "$CONF" ]; then
  sed "s/^MODE=.*/MODE=$MODE/" "$SCRIPT_DIR/updater.conf.example" >"$CONF"
  chown "$RUN_USER": "$CONF"
  echo "Creato $CONF"
fi
[ "$MODE" != vm ] || grep -q '^VM_DEPLOY_CMD=' "$CONF" ||
  echo "Attenzione: in modalità vm imposta VM_DEPLOY_CMD, VM_STOP_CMD e VM_DATABASE_URL in $CONF"

# Cartella condivisa (montata nel container api come /updater-data) e backup
DATA_DIR=$APP_DIR/updater-data
BACKUP_DIR=$APP_DIR/backups
mkdir -p "$DATA_DIR" "$BACKUP_DIR"
chown "$RUN_USER": "$DATA_DIR" "$BACKUP_DIR"
chmod 775 "$DATA_DIR"
chmod 750 "$BACKUP_DIR"
if [ ! -f "$DATA_DIR/settings.json" ]; then
  echo '{"auto_update": false, "branch": "main", "channel": "stable", "check_interval_minutes": 60, "keep_backups": 10, "backup_daily": true, "backup_time": "02:30", "backup_keep_days": 14}' >"$DATA_DIR/settings.json"
  chown "$RUN_USER": "$DATA_DIR/settings.json"
  chmod 664 "$DATA_DIR/settings.json"
fi
chmod +x "$SCRIPT_DIR/updater.sh"

# ---------------------------------------------------------------------------------------- accesso a GitHub
url=$( [ "$MODE" = image ] || as_user git -C "$APP_DIR" remote get-url origin 2>/dev/null || true)
key_ok=false
if [ "$MODE" = image ]; then
  key_ok=true # niente git: le versioni nuove arrivano dal registro delle immagini
elif [[ $url == https://* ]]; then
  echo
  echo "Il repo usa HTTPS ($url): con la deploy key serve l'indirizzo SSH. Esegui:"
  echo "  git -C $APP_DIR remote set-url origin $(sed -E 's#https://([^/]+)/(.*)#git@\1:\2#; s#(\.git)?$#.git#' <<<"$url")"
elif as_user git -C "$APP_DIR" ls-remote --heads origin >/dev/null 2>&1; then
  key_ok=true
  echo "Accesso a GitHub: ok ($url)"
fi
if ! $key_ok; then
  cat <<EOF

== Deploy key (chiave SSH di sola lettura per il repo privato), da fare una volta:
  1. Crea la chiave come utente $RUN_USER:
       ssh-keygen -t ed25519 -N "" -C "netmap-updater" -f $RUN_HOME/.ssh/netmap_deploy
  2. Su GitHub: repo → Settings → Deploy keys → Add deploy key, incolla il contenuto di
       $RUN_HOME/.ssh/netmap_deploy.pub
     e lascia SPENTA l'opzione "Allow write access".
  3. Di' a ssh di usarla per github.com, aggiungendo a $RUN_HOME/.ssh/config:
       Host github.com
         IdentityFile $RUN_HOME/.ssh/netmap_deploy
         IdentitiesOnly yes
     (oppure imposta GIT_SSH_KEY in $CONF)
  4. Prova: git -C $APP_DIR fetch origin
  Poi rilancia questo script.
EOF
fi

# ---------------------------------------------------------------------------------------- versione e avvio
as_user "$SCRIPT_DIR/updater.sh" version-env

if has_systemd; then
  cat >"/etc/systemd/system/$UNIT.service" <<EOF
[Unit]
Description=NetMap: controllo e installazione degli aggiornamenti
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=$SCRIPT_DIR/updater.sh
TimeoutStartSec=2h
EOF
  cat >"/etc/systemd/system/$UNIT.timer" <<EOF
[Unit]
Description=NetMap: giro dell'updater ogni minuto (il controllo vero segue l'intervallo impostato nell'app)

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF
  rm -f "/etc/cron.d/$UNIT"
  systemctl daemon-reload
  systemctl enable --now "$UNIT.timer"
  echo "Timer systemd attivo: systemctl list-timers $UNIT.timer — log: journalctl -u $UNIT"
else
  echo "* * * * * $RUN_USER $SCRIPT_DIR/updater.sh >/dev/null 2>&1" >"/etc/cron.d/$UNIT"
  chmod 644 "/etc/cron.d/$UNIT"
  echo "Cron attivo: /etc/cron.d/$UNIT"
fi

cat <<EOF

== Fatto. Ultimi passi:
  - Riavvia l'app perché legga version.env e la cartella condivisa (con deploy/install.sh l'ha già fatto lui):
      cd $APP_DIR && docker compose up -d
  - Apri NetMap come amministratore → Amministrazione → Aggiornamenti.
  - Log: $DATA_DIR/updater.log — backup del database: $BACKUP_DIR
EOF
