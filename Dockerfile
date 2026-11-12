# 留学 Agent 控制台 —— 单容器镜像
#
# 构建：docker build -t study-abroad-agent:1.1 .
# 运行：docker run -d --name agent -p 8000:8000 \
#         -e AUTH_SECRET=$(openssl rand -hex 32) \
#         -v %cd%/runtime:/app/runtime -v %cd%/logs:/app/logs \
#         study-abroad-agent:1.1
# 或者直接用 compose：docker compose up -d --build
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 非 root 运行：容器被攻破时损失最小
RUN useradd -m -u 10001 appuser

# 先装依赖（利用层缓存；requirements 变了才重装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码与数据
COPY ai_agent_core ./ai_agent_core
COPY web ./web
COPY data ./data
COPY scripts ./scripts
COPY .env.example ./

RUN mkdir -p /app/runtime /app/logs && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 健康检查用 Python，不额外装 curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

# 启动前灌库（幂等：同 source_id 覆盖），再起服务
CMD ["sh", "-c", "python scripts/ingest_seed.py && exec uvicorn ai_agent_core.main:app --host 0.0.0.0 --port 8000"]
