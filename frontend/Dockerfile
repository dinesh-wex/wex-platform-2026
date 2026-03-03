# WEx Platform Frontend - Multi-stage build for Cloud Run
# ============================================================================
# Dependencies Stage
# ============================================================================
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --production=false

# ============================================================================
# Build Stage
# ============================================================================
FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* env vars must be present at build time for Next.js to inline them
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

# ============================================================================
# Production Stage
# ============================================================================
FROM node:20-slim AS production
WORKDIR /app

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

ENV PORT=8080 \
    HOSTNAME="0.0.0.0" \
    NODE_ENV=production

EXPOSE 8080

CMD ["node", "server.js"]
