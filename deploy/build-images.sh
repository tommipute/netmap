#!/usr/bin/env bash
# Costruisce (e con --push pubblica) le immagini di una release: lo lancia il workflow di GitHub al tag vX.Y.Z,
# ma funziona anche a mano (es. verso un registro di prova).
#
#   deploy/build-images.sh 1.2.0 [PREFISSO] [--push]     PREFISSO predefinito: ghcr.io/tommipute/netmap
#
# Immagini: PREFISSO-backend e PREFISSO-web. Tag: la versione, più i canali seguiti dall'updater:
#   versione normale (1.2.0)      → 1.2.0, 1.2, stable, beta, latest
#   pre-release (1.2.0-rc.1)      → 1.2.0-rc.1, beta
# Nell'immagine backend finiscono anche i file d'installazione (/app/deploy): questa cartella, senza questo
# script, più updater/updater.sh, install.sh e updater.conf.example.

set -euo pipefail

VERSION=${1:?uso: $0 VERSIONE [PREFISSO] [--push]}
VERSION=${VERSION#v}
PREFIX=${2:-ghcr.io/tommipute/netmap}
PUSH=false
[ "${3:-${2:-}}" = --push ] && PUSH=true
[ "$PREFIX" = --push ] && PREFIX=ghcr.io/tommipute/netmap
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] || { echo "Versione non valida: $VERSION (es. 1.2.0 o 1.2.0-rc.1)" >&2; exit 1; }

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
COMMIT=$(git rev-parse HEAD)
DATE=$(git show -s --format=%cI HEAD)

if [[ $VERSION == *-* ]]; then
  TAGS=("$VERSION" beta)
else
  TAGS=("$VERSION" "${VERSION%.*}" stable beta latest)
fi

BUNDLE=$(mktemp -d)
trap 'rm -rf "$BUNDLE"' EXIT
cp -r deploy/. "$BUNDLE/"
rm -f "$BUNDLE/build-images.sh"
mkdir -p "$BUNDLE/updater"
cp updater/updater.sh updater/install.sh updater/updater.conf.example "$BUNDLE/updater/"
chmod 755 "$BUNDLE/install.sh" "$BUNDLE/updater/"*.sh

args=(--build-arg "APP_VERSION=$VERSION" --build-arg "APP_COMMIT=$COMMIT" --build-arg "APP_COMMIT_DATE=$DATE")
backend_tags=() web_tags=()
for t in "${TAGS[@]}"; do
  backend_tags+=(-t "$PREFIX-backend:$t")
  web_tags+=(-t "$PREFIX-web:$t")
done

echo "== NetMap $VERSION (${COMMIT:0:7}) → $PREFIX-{backend,web}: ${TAGS[*]}"
docker build --target release --build-context "deploy=$BUNDLE" --build-arg REQUIREMENTS=requirements.txt \
  "${args[@]}" "${backend_tags[@]}" backend
docker build --build-arg "VITE_APP_VERSION=$VERSION" --build-arg "APP_COMMIT=$COMMIT" "${web_tags[@]}" frontend

if $PUSH; then
  for t in "${TAGS[@]}"; do
    docker push -q "$PREFIX-backend:$t"
    docker push -q "$PREFIX-web:$t"
  done
  echo "== Pubblicate"
fi
