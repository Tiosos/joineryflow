FROM node:20-slim
RUN corepack enable
WORKDIR /code
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install || true
COPY . .
