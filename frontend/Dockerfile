# DialogAI web: the built React app behind nginx, which also proxies /api (and the call
# WebSocket) to the API. Built by deploy/docker-compose.yml.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Unprivileged nginx: runs as a non-root user and listens on 8080 (8443 with TLS).
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY nginx/http.conf.template /etc/nginx/templates/default.conf.template
# Where the API is; the LAN override points it at 127.0.0.1:8000 (host network).
ENV API_UPSTREAM=api:8000
EXPOSE 8080
