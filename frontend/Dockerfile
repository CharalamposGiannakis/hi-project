FROM node:22.23.2-alpine3.23 AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY examples/s1.json /app/examples/s1.json
ENV VITE_API_URL=/api
RUN npm run build

FROM caddy:2.11.6-alpine
COPY --from=build /app/frontend/dist/ /srv/
COPY infra/Caddyfile /etc/caddy/Caddyfile
