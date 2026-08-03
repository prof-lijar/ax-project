# syntax=docker/dockerfile:1.7

FROM node:22-alpine

ENV NODE_ENV=development

WORKDIR /app
RUN chown node:node /app

USER node

COPY --chown=node:node package.json package-lock.json ./
RUN --mount=type=cache,target=/home/node/.npm,uid=1000,gid=1000 \
    npm ci

COPY --chown=node:node . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
