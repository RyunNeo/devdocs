FROM node:22-slim AS builder

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --include=dev

COPY apps/web/ ./apps/web/
COPY packages/shared/ ./packages/shared/
ENV NODE_ENV=production \
    DEPLOY_STANDALONE=1 \
    API_BASE_URL=http://api:8000 \
    SESSION_COOKIE_NAME=devdocs_rehearsal_session
RUN npm run build --workspace @devdocs/web

FROM node:22-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && chown 10001:10001 /app

COPY --from=builder --chown=10001:10001 /app/apps/web/.next/standalone ./
COPY --from=builder --chown=10001:10001 /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=10001:10001 /app/apps/web/public ./apps/web/public

USER 10001:10001
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
