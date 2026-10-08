# Produzione (docker-compose.prod.yml): interfaccia compilata e servita da nginx, che inoltra /api al container api.
# In sviluppo non si usa: il container web lancia Vite sui sorgenti montati.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
