FROM node:20-slim

WORKDIR /app

# Copy dependency manifests first (layer cache)
COPY ClawRoute/package.json ClawRoute/package-lock.json* ./

RUN npm ci --omit=dev

# Copy source and build
COPY ClawRoute/ ./

RUN npm run build

# Ensure data directory exists for persistence
RUN mkdir -p /app/data && chown node:node /app/data

# Remove dev source after build (keep dist/ and node_modules/)
RUN rm -rf src/ test/ tsconfig.json

USER node

EXPOSE 18790

ENV NODE_ENV=production
ENV CLAWROUTE_HOST=0.0.0.0
ENV CLAWROUTE_PORT=18790

CMD ["node", "dist/index.js"]
