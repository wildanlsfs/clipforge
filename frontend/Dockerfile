FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# curl for the docker-compose healthcheck -- nginx:alpine doesn't ship wget
# or curl by default (confirmed live: the container ran fine but was marked
# unhealthy, which made Coolify's proxy refuse to route to it at all).
RUN apk add --no-cache curl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
