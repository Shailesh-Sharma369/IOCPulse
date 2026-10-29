# syntax=docker/dockerfile:1.4
# =============================================================================
# IOC Pulse — Frontend Dockerfile (multi-stage)
# =============================================================================
# CACHING NOTE:
#   --mount=type=cache,target=/root/.npm keeps npm's download cache in a
#   Docker-managed volume that survives rebuilds. Combined with the COPY
#   ordering below, a normal code change rebuilds in ~10-20 seconds.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — Build the React/Vite bundle
# -----------------------------------------------------------------------------
FROM node:18-alpine AS build

WORKDIR /app

# Vite bakes VITE_* into the bundle at build time.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

# Copy manifests first so the npm install layer is cached across code changes.
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

# Copy source and produce the production bundle
COPY . .
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2 — Serve via nginx (with SPA fallback for React Router)
# -----------------------------------------------------------------------------
FROM nginx:alpine

RUN cat > /etc/nginx/conf.d/default.conf <<'EOF'
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(?:js|css|png|jpg|jpeg|gif|svg|ico|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]