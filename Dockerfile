FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install project dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application files
COPY . .

EXPOSE 8000 8501
