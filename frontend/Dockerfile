# Produzione: interfaccia compilata e servita da nginx, che inoltra /api al container api.
# In sviluppo non si usa: il container web lancia Vite sui sorgenti montati.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Immagini pubblicate: il numero di versione mostrato in basso (vuoto = quello di src/version.js)
ARG VITE_APP_VERSION=""
ENV VITE_APP_VERSION=${VITE_APP_VERSION}
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
ARG VITE_APP_VERSION=""
ARG APP_COMMIT=""
LABEL org.opencontainers.image.title="NetMap (interfaccia)" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/tommipute/netmap" \
      org.opencontainers.image.version=${VITE_APP_VERSION} \
      org.opencontainers.image.revision=${APP_COMMIT}
