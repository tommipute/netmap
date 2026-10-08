FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ping per il monitor dello stato live (fase 4)
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Sviluppo: include pytest e il simulatore SNMP per i test; in produzione REQUIREMENTS=requirements.txt
ARG REQUIREMENTS=requirements-dev.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS}
COPY . .

CMD ["sh", "start.sh"]

# Immagine pubblicata (deploy/build-images.sh, al tag vX.Y.Z): versione scritta dentro e file di installazione in
# /app/deploy (contesto "deploy" passato da build-images.sh), da cui li prendono install.sh e l'updater.
FROM base AS release
RUN rm -rf tests pytest.ini requirements-dev.txt
COPY --from=deploy . /app/deploy/
ARG APP_VERSION=""
ARG APP_COMMIT=""
ARG APP_COMMIT_DATE=""
ENV APP_VERSION=${APP_VERSION} \
    APP_COMMIT=${APP_COMMIT} \
    APP_COMMIT_DATE=${APP_COMMIT_DATE} \
    APP_TAG=v${APP_VERSION}
LABEL org.opencontainers.image.title="NetMap" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/tommipute/netmap" \
      org.opencontainers.image.version=${APP_VERSION} \
      org.opencontainers.image.revision=${APP_COMMIT} \
      io.netmap.commit-date=${APP_COMMIT_DATE}

# Ultimo stadio = quello che compose costruisce in sviluppo e in docker-compose.prod.yml (lo stadio release non
# viene nemmeno considerato, quindi non serve il contesto "deploy")
FROM base AS dev
