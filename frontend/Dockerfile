# syntax=docker/dockerfile:1
# Optional: --secret id=extra_ca,src=<ca-bundle.pem> when building behind a TLS-inspecting proxy.
# Build the SPA, then serve it with nginx (which also proxies /api to the API container).
# Built from deploy/docker-compose.yml, which supplies the "deploy" build context for nginx.conf.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY --from=deploy nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
