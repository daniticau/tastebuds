FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

# Install exactly what uv.lock pins. The tests ran against these versions,
# so production must not drift to a newer major release on its own.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY migrations/ migrations/
RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

RUN adduser --disabled-password --gecos "" appuser
USER appuser

CMD ["sh", "-c", "uvicorn tastebuds.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
