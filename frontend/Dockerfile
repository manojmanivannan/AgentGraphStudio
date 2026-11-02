# Multi-stage production Dockerfile for AgentGraphStudio Frontend

# Stage 1: Install dependencies
# node:26.12.1 is the Node.js security release that backports the Brotli fix
# for CVE-2026-111497 (process.versions.brotli still reports 1.2.0).
FROM node:26.13.0-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Stage 2: Development stage (optional target for local containerized dev)
FROM deps AS dev
WORKDIR /app
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 3: Build static production assets
FROM deps AS builder
WORKDIR /app
ARG VITE_USE_PROXY=true
ARG VITE_API_HOST=""
ENV VITE_USE_PROXY=$VITE_USE_PROXY
ENV VITE_API_HOST=$VITE_API_HOST
COPY . .
RUN npm run build

# Stage 4: Lightweight production server using Nginx
FROM nginx:alpine AS runner

# nginx:alpine (Alpine 3.24) ships brotli/brotli-libs 1.2.0-r1, whose decoder
# has an out-of-bounds write fixed in 1.2.1 (CVE-2026-111497), plus a vulnerable
# curl/libcurl 8.22.0-r0 (CVE-2026-92392). The brotli libraries are present even
# though nginx.conf enables gzip only, so upgrade the whole Alpine package set to
# pick up the patched builds (brotli 1.2.1-r0, curl 8.23.0-r0) instead of leaving
# vulnerable shared libraries on disk. Combined with the cleanup to keep one layer.
RUN apk upgrade --no-cache \
    && rm -rf /usr/share/nginx/html/*

# Copy built frontend assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy production nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP and default studio ports
EXPOSE 80 5173

# Container healthcheck
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:80/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
