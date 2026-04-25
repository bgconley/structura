FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json

RUN npm ci --workspace apps/web

COPY apps/web apps/web

ARG VITE_STRUCTURA_API_BASE_URL=
ENV VITE_STRUCTURA_API_BASE_URL=${VITE_STRUCTURA_API_BASE_URL}

RUN npm --workspace apps/web run build

FROM node:20-alpine

ENV NODE_ENV=production \
    PORT=3000 \
    STRUCTURA_API_UPSTREAM=http://api:8000

WORKDIR /app

RUN chown -R node:node /app

USER node

COPY --from=build --chown=node:node /app/apps/web/dist ./dist
COPY --from=build --chown=node:node /app/apps/web/server.mjs ./server.mjs

EXPOSE 3000

CMD ["node", "server.mjs"]
