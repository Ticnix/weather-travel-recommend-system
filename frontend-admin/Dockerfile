# 管理端（Vue3 + Vite）生产镜像
# 多阶段构建：Node 构建静态资源 → Nginx 托管并反向代理 /api
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
# 使用国内 npm 镜像加速（如需切回官方源，去掉 --registry 参数即可）
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
