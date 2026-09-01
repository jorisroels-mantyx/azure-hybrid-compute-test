FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml .
RUN uv sync --no-cache
COPY train.py .
ENV N_ESTIMATORS=100
CMD ["uv", "run", "python", "train.py"]
