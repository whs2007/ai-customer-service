# 多阶段构建：builder 安装依赖，运行镜像仅保留产物，且以非 root 用户运行
FROM python:3.12-slim AS builder

WORKDIR /build

# 先拷贝构建所需文件（源码层变更不触发依赖重装，利于层缓存）
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    STORAGE_DIR=/app/storage

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# 非 root 运行 + 存储目录可写（compose 挂载的命名卷会继承该目录属主）
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 迁移/引导在 compose migrate 服务中执行（见 docker-compose.yml）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
