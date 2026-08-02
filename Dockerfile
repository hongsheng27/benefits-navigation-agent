# Multi-stage Dockerfile for benefits-navigation-agent
# Stage 1: Build frontend
FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Build with the EC2 backend URL
ARG VITE_API_BASE_URL=http://35.88.159.212:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Stage 2: Backend + serve frontend via nginx
FROM python:3.13-slim AS runtime

# Install nginx and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock* ./
RUN pip install --no-cache-dir \
    boto3>=1.43.62 \
    fastapi>=0.115 \
    "psycopg[binary]==3.2.9" \
    psycopg-pool==3.2.6 \
    pydantic-settings>=2.5 \
    "uvicorn[standard]>=0.30"

# Copy backend source
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Copy data files
COPY data/ /app/data/

# Nginx config: serve frontend on port 80, proxy /sessions to backend
RUN cat > /etc/nginx/sites-available/default << 'EOF'
server {
    listen 80;
    server_name _;

    # Frontend (static files)
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # Backend API proxy
    location /sessions {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
}
EOF

# Startup script
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
set -e
# Start backend in background
cd /app/backend
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 &

# Start nginx in foreground
nginx -g "daemon off;"
EOF
RUN chmod +x /app/start.sh

# --- Database configuration (connect to RDS by default) ---
ENV DATA_STORE_BACKEND=postgresql
ENV RDS_HOST=database-1.c54m4aak2pcn.us-west-2.rds.amazonaws.com
ENV RDS_PORT=5432
ENV RDS_DATABASE=benefits_navigation
ENV RDS_USERNAME=benefits_admin
ENV RDS_SSLMODE=require
# RDS_PASSWORD must be injected at runtime via docker run -e or ECS task definition

EXPOSE 80 8000

CMD ["/app/start.sh"]
