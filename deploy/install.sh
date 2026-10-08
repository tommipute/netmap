#!/usr/bin/env bash
# Installa NetMap su un server Linux con Docker, usando le immagini già pronte (niente codice sorgente, niente build).
#
#   docker run --rm ghcr.io/tommipute/netmap-backend:stable cat /app/deploy/install.sh > install-netmap.sh
#   sudo bash install-netmap.sh [opzioni]
#
# Opzioni:
#   --address URL    indirizzo con cui si apre NetMap (predefinito: https://<IP del server>); http://... = senza HTTPS
#   --tls VALORE     certificato: "tls internal" (predefinito), "tls email@dominio" (Let's Encrypt),
#                    "tls /certs/netmap.crt /certs/netmap.key" (certificato vostro, copiato in <dir>/certs)
#   --dir CARTELLA   dove installare (predefinito /opt/netmap)
#   --channel C      stable (predefinito) o beta
#   --image PREFISSO registro delle immagini (predefinito ghcr.io/tommipute/netmap)
#   --user UTENTE    utente che fa girare gli aggiornamenti (predefinito: chi ha lanciato sudo); deve poter usare docker
#
# Rilanciarlo su un'installazione esistente non tocca .env, database e backup: sistema solo file e timer.

set -euo pipefail

DIR=/opt/netmap
ADDRESS=
TLS="tls internal"
CHANNEL=stable
IMAGE=ghcr.io/tommipute/netmap
RUN_USER=${SUDO_USER:-root}

while [ $# -gt 0 ]; do
  case $1 in
    --address) ADDRESS=${2:-}; shift 2 ;;
    --tls) TLS=${2:-}; shift 2 ;;
    --dir) DIR=${2:-}; shift 2 ;;
    --channel) CHANNEL=${2:-}; shift 2 ;;
    --image) IMAGE=${2:-}; shift 2 ;;
    --user) RUN_USER=${2:-}; shift 2 ;;
    -h | --help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $1 (vedi --help)" >&2; exit 1 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
fail() { echo "ERRORE: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "lancialo con sudo: sudo bash $0 $*"
[[ $CHANNEL =~ ^(stable|beta)$ ]] || fail "--channel deve essere stable o beta"
id "$RUN_USER" >/dev/null 2>&1 || fail "l'utente $RUN_USER non esiste"

# ------------------------------------------------------------------------------------------------ programmi
say "Controllo i programmi necessari"
command -v docker >/dev/null || fail "manca Docker. Installalo con: curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 || fail "manca il plugin docker compose v2 (pacchetto docker-compose-plugin)"
missing=()
for cmd in jq curl flock; do command -v "$cmd" >/dev/null || missing+=("$cmd"); done
if [ ${#missing[@]} -gt 0 ]; then
  command -v apt-get >/dev/null || fail "mancano ${missing[*]}: installali e rilancia"
  pkgs=$(printf '%s\n' "${missing[@]}" | sed 's/^flock$/util-linux/' | sort -u | tr '\n' ' ')
  echo "Installo $pkgs"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $pkgs >/dev/null
fi
if [ "$RUN_USER" != root ] && ! id -nG "$RUN_USER" | grep -qw docker; then
  usermod -aG docker "$RUN_USER"
  echo "Aggiunto $RUN_USER al gruppo docker (serve all'updater)"
fi

# ---------------------------------------------------------------------------------------------- immagini
say "Scarico NetMap ($IMAGE, canale $CHANNEL)"
docker pull -q "$IMAGE-backend:$CHANNEL" >/dev/null ||
  fail "non riesco a scaricare $IMAGE-backend:$CHANNEL (registro privato? docker login ghcr.io)"
VERSION=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$IMAGE-backend:$CHANNEL")
[ -n "$VERSION" ] || fail "l'immagine non dice la sua versione"
echo "Versione $VERSION"

mkdir -p "$DIR" "$DIR/certs"
docker run --rm --entrypoint tar "$IMAGE-backend:$VERSION" -C /app/deploy -cf - . 2>/dev/null | tar -xf - -C "$DIR" --no-same-owner ||
  { docker pull -q "$IMAGE-backend:$VERSION" >/dev/null &&
    docker run --rm --entrypoint tar "$IMAGE-backend:$VERSION" -C /app/deploy -cf - . | tar -xf - -C "$DIR" --no-same-owner; } ||
  fail "non riesco a estrarre i file di installazione dall'immagine"
chmod +x "$DIR/install.sh" "$DIR/updater/"*.sh
chown -R "$RUN_USER": "$DIR"
# data/ (chiave dei segreti) la scrivono i container, che girano come root: nessun altro la legge
mkdir -p "$DIR/data"
chown root: "$DIR/data"
chmod 700 "$DIR/data"

# ------------------------------------------------------------------------------------------------- .env
if [ -f "$DIR/.env" ]; then
  say "Trovato $DIR/.env: lo tengo così com'è"
  VERSION=$(sed -n 's/^NETMAP_VERSION=//p' "$DIR/.env" | tail -n1)
else
  say "Creo $DIR/.env"
  if [ -z "$ADDRESS" ]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    ADDRESS=https://${ip:-$(hostname -f)}
  fi
  [[ $ADDRESS == http://* || $ADDRESS == https://* ]] || ADDRESS=https://$ADDRESS
  secure=true
  if [[ $ADDRESS == http://* ]]; then
    TLS=
    secure=false
  fi
  password=$(od -An -tx1 -N24 /dev/urandom | tr -d ' \n') # niente "| head": con pipefail chiuderebbe la pipe in errore
  scheme=${ADDRESS%%://*}
  host=${ADDRESS#*://}
  host=${host%%/*}
  sed -e "s|^NETMAP_HOST=.*|NETMAP_HOST=$host|" \
    -e "s|^NETMAP_SCHEME=.*|NETMAP_SCHEME=$scheme|" \
    -e "s|^NETMAP_TLS=.*|NETMAP_TLS=$TLS|" \
    -e "s|^COOKIE_SECURE=.*|COOKIE_SECURE=$secure|" \
    -e "s|^NETMAP_VERSION=.*|NETMAP_VERSION=$VERSION|" \
    -e "s|^NETMAP_IMAGE=.*|NETMAP_IMAGE=$IMAGE|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$password|" \
    "$DIR/env.example" >"$DIR/.env"
  chown "$RUN_USER": "$DIR/.env"
  chmod 600 "$DIR/.env"
fi

# ------------------------------------------------------------------------------------------------ avvio
say "Avvio NetMap"
cd "$DIR"
docker compose pull -q
docker compose up -d --remove-orphans

# Updater (timer systemd): impostazioni e canale si cambiano poi dall'app, pagina Aggiornamenti
say "Installo l'updater"
[ -f "$DIR/updater-data/settings.json" ] ||
  { mkdir -p "$DIR/updater-data" && echo "{\"channel\": \"$CHANNEL\"}" >"$DIR/updater-data/settings.json"; }
chown -R "$RUN_USER": "$DIR/updater-data"
chmod 664 "$DIR/updater-data/settings.json"
SUDO_USER=$RUN_USER bash "$DIR/updater/install.sh" --mode image >/dev/null
echo "Timer systemd netmap-updater attivo (canale $CHANNEL)"

say "Aspetto che NetMap risponda"
ok=false
for _ in $(seq 60); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" 2>/dev/null; then
    ok=true
    break
  fi
  sleep 3
done
$ok || fail "NetMap non risponde dopo 3 minuti: guarda i log con  cd $DIR && docker compose logs api"

ADDRESS=$(sed -n 's/^NETMAP_SCHEME=//p' .env | tail -n1)://$(sed -n 's/^NETMAP_HOST=//p' .env | tail -n1)
TLS=$(sed -n 's/^NETMAP_TLS=//p' .env | tail -n1)
cat <<EOF

== NetMap $VERSION installato in $DIR
  Apri $ADDRESS : al primo accesso crei l'amministratore.
EOF
if [ "$TLS" = "tls internal" ]; then
  cat <<EOF
  Il certificato è firmato dalla CA interna di Caddy: il browser avvisa finché non la installi nei PC.
    cd $DIR && docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt netmap-ca.crt
  Su Windows: doppio clic su netmap-ca.crt → Installa certificato → Computer locale →
  "Autorità di certificazione radice attendibili" (oppure distribuiscila con un criterio di gruppo).
EOF
fi
cat <<EOF
  Aggiornamenti e backup: NetMap → Amministrazione. Impostazioni del server: $DIR/.env (poi docker compose up -d).
  Tieni al sicuro, insieme ai backup in $DIR/backups, il file .env e la cartella data/: senza la chiave
  i profili SNMP di un database ripristinato vanno reinseriti.
EOF
