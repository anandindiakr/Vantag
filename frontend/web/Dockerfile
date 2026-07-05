# Playwright's official image ships a Chromium build matched to the
# playwright npm version (see package.json) plus all OS-level shared libs
# it needs. This avoids trying to hand-install Chromium deps on Alpine
# (playwright's --with-deps installer only supports apt/dnf, not apk).
# This stage is discarded after build, so it does not affect final image size.
FROM mcr.microsoft.com/playwright:v1.47.0-jammy AS builder
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .

# Which production domain to bake into canonical/OG/hreflang/JSON-LD URLs
# during prerender. Override per-region at build time, e.g.:
#   docker build --build-arg PRERENDER_BASE_URL=https://retail-vantag.com .
#   docker build --build-arg PRERENDER_BASE_URL=https://jagajaga.my .
ARG PRERENDER_BASE_URL=https://retailnazar.com
ENV PRERENDER_BASE_URL=$PRERENDER_BASE_URL

RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
