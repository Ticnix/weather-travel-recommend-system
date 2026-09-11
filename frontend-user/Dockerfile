# 用户端（React19 + Vite）生产镜像
# 多阶段构建：Node 构建静态资源 → Nginx 托管并反向代理 /api
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine

# 构建产物作为静态资源
COPY --from=builder /app/dist /usr/share/nginx/html
# 覆盖默认站点配置：SPA 路由回退 + API 代理 + SSE 支持
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
