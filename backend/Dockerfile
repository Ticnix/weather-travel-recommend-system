# 后端镜像：用于运行 FastAPI（uvicorn）与 Celery worker
FROM python:3.12-slim

WORKDIR /app

# 系统依赖（psycopg 等可能需要编译头文件）
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认命令由 docker-compose 的 command 覆盖
CMD ["python", "-m", "app.main"]
