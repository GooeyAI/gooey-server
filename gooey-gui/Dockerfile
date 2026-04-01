# base node image
FROM node:20-bookworm-slim

# Copied from https://github.com/puppeteer/puppeteer/blob/aefbde60d7993c37ca5289e034f3ca90945c20ff/docker/Dockerfile#L6
#
# Install latest chrome dev package and fonts to support major charsets (Chinese, Japanese, Arabic, Hebrew, Thai and a few others)
# Note: this installs the necessary libs to make the bundled version of Chrome that Puppeteer
# installs, work.
RUN apt-get update \
    && apt-get install -y wget gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-khmeros fonts-kacst fonts-freefont-ttf libxss1 \
      --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm i -g npm@latest && npm ci --verbose

ARG SENTRY_ORG
ENV SENTRY_ORG=$SENTRY_ORG
ARG SENTRY_PROJECT
ENV SENTRY_PROJECT=$SENTRY_PROJECT
ARG SENTRY_AUTH_TOKEN
ENV SENTRY_AUTH_TOKEN=$SENTRY_AUTH_TOKEN
ARG CAPROVER_GIT_COMMIT_SHA
ENV SENTRY_RELEASE=$CAPROVER_GIT_COMMIT_SHA
ARG WIX_URLS
ENV WIX_URLS=$WIX_URLS

COPY . .
RUN SENTRY_LOG_LEVEL=debug npm run build-prod

ENV NODE_ENV=production

HEALTHCHECK CMD wget 127.0.0.1:3000/__/health || exit 1

CMD ./scripts/run-prod.sh
