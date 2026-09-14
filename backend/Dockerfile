# 后端镜像：用于运行 FastAPI（uvicorn）与 Celery worker
FROM python:3.12-slim

WORKDIR /app

# 系统依赖（psycopg 等可能需要编译头文件）
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 使用国内 PyPI 镜像加速（如需切回官方源，去掉 -i 参数即可）
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# 启动 FastAPI（app.main 无 __main__ 入口，必须显式用 uvicorn）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
