# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npm run build:prod

# Runtime stage
FROM node:20-alpine

WORKDIR /app

RUN npm install -g http-server

# Copy built application from builder
COPY --from=builder /app/dist/tracewise-frontend ./dist/tracewise-frontend

# Copy config file for runtime
COPY --from=builder /app/src/assets/config.json ./dist/tracewise-frontend/assets/config.json

EXPOSE 4200

# Serve the application
CMD ["http-server", "dist/tracewise-frontend", "-p", "4200", "-c-1", "-g"]
