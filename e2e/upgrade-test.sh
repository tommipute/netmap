#!/usr/bin/env bash
# Prova di installazione e aggiornamento come la vive chi usa NetMap. La lancia il workflow "Test" di GitHub; gira
# anche a mano su una macchina di prova con Docker e sudo, ma NON su un server con NetMap già installato (usa le
# porte 80 e 443 e il timer netmap-updater).
#
#   1. installa l'ultima versione pubblicata (FROM_IMAGE, canale beta) con il suo install.sh
#   2. crea l'amministratore e un po' di dati
#   3. costruisce le immagini del codice attuale come versione NEW_VERSION in un registro locale
#   4. chiede l'aggiornamento come fa la pagina Aggiornamenti e aspetta che l'updater (timer) finisca
#   5. controlla esito, versione installata e dati
# Senza versioni pubblicate (o con FROM_IMAGE=none) prova solo l'installazione da zero del codice attuale.
#
#   e2e/upgrade-test.sh            prova completa (poi: cd e2e && npx playwright test)
#   e2e/upgrade-test.sh --clean    toglie l'installazione di prova e il registro locale
#
# Alla fine scrive in e2e/.upgrade-test.env le variabili per i test nel browser (NETMAP_EXPECT_VERSION...).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DIR=${DIR:-/opt/netmap-e2e}
FROM_IMAGE=${FROM_IMAGE:-ghcr.io/tommipute/netmap}
REGISTRY=${REGISTRY:-localhost:5000}
NEW_VERSION=${NEW_VERSION:-99.0.0-e2e.$(date +%s)}
ADMIN=${NETMAP_USER:-admin}
PASSWORD=${NETMAP_PASSWORD:-ProvaE2E-2026}
LOCAL=$REGISTRY/netmap
URL=https://localhost
RUN_USER=$(id -un)
TOKEN=

say() { printf '\n== %s\n' "$*"; }
fail() {
  echo "ERRORE: $*" >&2
  exit 1
}
api() { # metodo percorso [json]
  curl -sk --fail-with-body -X "$1" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    ${3:+--data "$3"} "$URL/api$2"
}
status() { jq -r "$1" "$DIR/updater-data/status.json" 2>/dev/null; }

clean() {
  if [ -d "$DIR" ]; then
    (cd "$DIR" && sudo docker compose down -v -t 5 >/dev/null 2>&1) || true
    sudo bash "$DIR/updater/install.sh" --uninstall >/dev/null 2>&1 || true
    sudo rm -rf "$DIR"
  fi
  docker rm -f netmap-e2e-registry >/dev/null 2>&1 || true
}

if [ "${1:-}" = --clean ]; then
  clean
  echo "Installazione di prova tolta"
  exit 0
fi
[ -d "$DIR" ] && clean

say "Registro locale $REGISTRY"
docker run -d --name netmap-e2e-registry -p "${REGISTRY##*:}:5000" registry:2 >/dev/null
for _ in $(seq 20); do curl -fs "http://$REGISTRY/v2/" >/dev/null && break; sleep 1; done

push_tags() { # immagine sorgente (senza -backend/-web), tag sorgente, tag di destinazione...
  local from=$1 tag=$2 part target
  shift 2
  for part in backend web; do
    docker pull -q "$from-$part:$tag" >/dev/null
    for target in "$@"; do
      docker tag "$from-$part:$tag" "$LOCAL-$part:$target"
      docker push -q "$LOCAL-$part:$target" >/dev/null
    done
  done
}

OLD=
if [ "$FROM_IMAGE" != none ] && docker pull -q "$FROM_IMAGE-backend:beta" >/dev/null 2>&1; then
  OLD=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$FROM_IMAGE-backend:beta")
  say "Versione di partenza: $OLD (da $FROM_IMAGE)"
  push_tags "$FROM_IMAGE" "$OLD" "$OLD" beta
else
  say "Nessuna versione pubblicata: provo solo l'installazione da zero di $NEW_VERSION"
  "$ROOT/deploy/build-images.sh" "$NEW_VERSION" "$LOCAL" --push
fi

say "Installazione con install.sh"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
docker run --rm "$LOCAL-backend:beta" cat /app/deploy/install.sh >"$WORK/install.sh"
sudo bash "$WORK/install.sh" --dir "$DIR" --channel beta --image "$LOCAL" --address "$URL" --user "$RUN_USER"
[ "$(sudo stat -c %a "$DIR/.env")" = 600 ] || fail ".env leggibile da altri"

say "Amministratore e dati di prova"
TOKEN=$(curl -sk --fail-with-body -H 'Content-Type: application/json' \
  --data "{\"username\": \"$ADMIN\", \"password\": \"$PASSWORD\"}" "$URL/api/auth/setup" | jq -r .token)
[ -n "$TOKEN" ] && [ "$TOKEN" != null ] || fail "creazione dell'amministratore non riuscita"
site=$(api POST /sites '{"name": "Sede prova aggiornamento"}' | jq .id)
core=$(api POST /devices "{\"name\": \"upg-core\", \"site_id\": $site, \"serial\": \"UPG-SN-1\"}" | jq .id)
access=$(api POST /devices "{\"name\": \"upg-access\", \"site_id\": $site}" | jq .id)
a=$(api POST /interfaces "{\"device_id\": $core, \"name\": \"Te1/1/1\"}" | jq .id)
b=$(api POST /interfaces "{\"device_id\": $access, \"name\": \"Te1/1/2\"}" | jq .id)
api POST /cables "{\"a_interface_id\": $a, \"b_interface_id\": $b}" >/dev/null
echo "Sede $site, device $core e $access collegati"

if [ -n "$OLD" ]; then
  say "Immagini del codice attuale: $NEW_VERSION"
  "$ROOT/deploy/build-images.sh" "$NEW_VERSION" "$LOCAL" --push

  say "Aggiornamento $OLD → $NEW_VERSION (richiesta come dalla pagina Aggiornamenti)"
  before=$(status '.history[0].finished_at // ""')
  printf '{"action": "update", "requested_at": "%s", "requested_by": "upgrade-test"}\n' "$(date -Iseconds)" \
    >"$DIR/updater-data/request.json"
  deadline=$(($(date +%s) + 900))
  while :; do
    finished=$(status '.history[0].finished_at // ""')
    [ -n "$finished" ] && [ "$finished" != "$before" ] && [ "$(status .activity)" = idle ] && break
    [ "$(date +%s)" -lt "$deadline" ] || fail "l'updater non ha finito in 15 minuti: $(status .activity_message)"
    sleep 5
  done
  outcome=$(status '.history[0].outcome')
  echo "Esito: $outcome. $(status '.history[0].message')"
  [ "$outcome" = success ] || { sudo cat "$DIR/updater-data/updater.log" >&2; fail "aggiornamento non riuscito"; }
  [ "$(status '.installed.version')" = "$NEW_VERSION" ] || fail "l'updater dice installata $(status '.installed.version')"
  ls "$DIR/backups/"netmap-*.dump >/dev/null 2>&1 || fail "manca il backup fatto prima dell'aggiornamento"
fi

say "Controlli finali"
version=$(curl -sk "$URL/api/version" | jq -r .version)
[ "$version" = "$NEW_VERSION" ] || fail "l'API dice versione $version, attesa $NEW_VERSION"
found=$(api GET "/devices?q=upg-" | jq .total)
[ "$found" = 2 ] || fail "dopo l'aggiornamento ci sono $found device di prova invece di 2"
cables=$(api GET "/devices/$core/ports" | jq '[.[] | select(.cable_id != null)] | length')
[ "$cables" = 1 ] || fail "il cavo di prova non c'è più"
curl -sk "$URL/" | grep -q '<div id="root">' || fail "l'interfaccia non risponde su $URL"
curl -s -o /dev/null -w '%{http_code}' "http://localhost/" | grep -q '^30[18]$' || fail "http non reindirizza a https"
echo "NetMap $version risponde, dati e cavo ci sono ancora"

# Per i test nel browser (e2e/tests): stessa installazione, stesso amministratore
cat >"$ROOT/e2e/.upgrade-test.env" <<EOF
NETMAP_URL=$URL
NETMAP_USER=$ADMIN
NETMAP_PASSWORD=$PASSWORD
NETMAP_EXPECT_VERSION=$NEW_VERSION
NETMAP_TEST_BACKUP=1
EOF
say "Prova riuscita${OLD:+: aggiornamento $OLD → $NEW_VERSION}"
