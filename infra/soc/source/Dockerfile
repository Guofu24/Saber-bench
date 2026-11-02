FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.12.12-slim-bookworm
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY . /app
RUN uv sync --frozen --no-dev && mkdir /data && chown 10001:10001 /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
