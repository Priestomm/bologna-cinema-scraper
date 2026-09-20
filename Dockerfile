FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dipendenze installate prima di copiare il codice applicativo: cambia solo
# quando cambiano pyproject.toml/uv.lock, cosi' questo layer resta in cache
# anche quando si modifica solo il codice.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p data logs

EXPOSE 8080

CMD ["python", "main.py"]
