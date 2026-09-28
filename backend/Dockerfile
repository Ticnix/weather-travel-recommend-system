# 后端镜像：用于运行 FastAPI（uvicorn）与 Celery worker
FROM python:3.12-slim

WORKDIR /app

# Python 依赖放在系统依赖**之前**：apt 层的改动（加一个 lib）会让后面所有层
# 缓存失效，于是每次调系统库都要把上百个 pip 包重下一遍——实测因此撞上镜像源
# 超时而构建失败。pip 在前、apt 在后，调系统库就只重跑一次 apt。
COPY requirements.txt .
# 使用国内 PyPI 镜像加速（如需切回官方源，去掉 -i 参数即可）
# pip 用 BuildKit 缓存挂载：这台机器到镜像源的网络抖动（DNS 间歇性解析失败），
# 失败重试时已下载的 wheel 不作废；主源挂了自动换备用源；超时放宽到 60s。
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt --timeout 60 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    || pip install -r requirements.txt --timeout 60 \
    -i https://mirrors.aliyun.com/pypi/simple/

# 系统依赖（psycopg 等可能需要编译头文件）
# libgl1 / libglib2.0-0 / libxcb1：opencv（离线 OCR 的依赖链）在 slim 镜像里
# 缺这些运行库会在 import 阶段直接 ImportError: libxcb.so.1，
# 表现为"OCR 引擎不可用"（不是识别不出，而是根本没加载起来）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# 预下载语音转写模型：放到这里（而不是运行时）是因为容器里往往连不上
# HuggingFace，第一条语音消息会一直卡在下载。用镜像站加速。
# **失败/超时都不阻断构建**——运行时仍会自动重试（见 asr_service 的惰性加载）；
# timeout 是必需的：网络慢时 download 会一直挂着，把整个构建拖死。
# 档位与 .env 的 ASR_LOCAL_MODEL 保持一致（base≈74MB；small≈461MB 更准但更慢）。
ENV HF_ENDPOINT=https://hf-mirror.com
ARG ASR_MODEL_NAME=base
RUN timeout 900 python -c "from faster_whisper import WhisperModel; WhisperModel('${ASR_MODEL_NAME}', device='cpu', compute_type='int8')" \
    || echo "语音模型未预下载成功（不影响启动），首次使用时会自动重试"

COPY . .

# 启动 FastAPI（app.main 无 __main__ 入口，必须显式用 uvicorn）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
