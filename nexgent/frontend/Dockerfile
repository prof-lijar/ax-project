# syntax=docker/dockerfile:1.7

FROM node:22-alpine

ENV NODE_ENV=development

WORKDIR /app
RUN chown node:node /app

COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/nexgent-frontend-entrypoint

USER node

COPY --chown=node:node package.json package-lock.json ./
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 \
    npm ci && \
    sha256sum package-lock.json | cut -d ' ' -f 1 > node_modules/.nexgent-package-lock.sha256

COPY --chown=node:node . .

EXPOSE 5173

ENTRYPOINT ["nexgent-frontend-entrypoint"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
