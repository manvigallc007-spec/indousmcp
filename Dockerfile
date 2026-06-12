# Image for the MCP server and the agent worker (same code, different command).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first (better layer caching), then the package.
# SQL migrations live under src/indo_usa_mcp/sql and ship as package data.
COPY pyproject.toml README.md ./
COPY src ./src
# Include the `semantic` extra (fastembed) so EMBEDDING_PROVIDER=fastembed works without a rebuild.
RUN pip install ".[semantic]"

# Default: stdio. The compose service overrides env + command for HTTP / worker.
CMD ["python", "-m", "indo_usa_mcp.server"]
