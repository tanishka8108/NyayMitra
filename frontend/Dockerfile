# ---------- Stage 1: Build ----------
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

RUN npm run build


# ---------- Stage 2: Production ----------
FROM nginx:alpine

# Remove default nginx configuration and website
RUN rm -rf /usr/share/nginx/html/* \
    /etc/nginx/conf.d/default.conf

# Copy production React build
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Create non-root user
RUN addgroup -S nyaymitra && \
    adduser -S nyaymitra -G nyaymitra

# Give the application user ownership of required runtime directories
RUN mkdir -p \
        /var/cache/nginx \
        /var/log/nginx \
        /var/run/nginx \
        /tmp/nginx \
    && chown -R nyaymitra:nyaymitra \
        /usr/share/nginx/html \
        /var/cache/nginx \
        /var/log/nginx \
        /var/run/nginx \
        /tmp/nginx \
        /tmp

USER nyaymitra

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]