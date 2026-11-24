FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
# Le modèle est rendu au démarrage ; seules les variables API_* sont substituées.
ENV NGINX_ENVSUBST_FILTER=^API_ \
    API_UPSTREAM=http://api:8000 \
    API_HOST_HEADER=\$host
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
