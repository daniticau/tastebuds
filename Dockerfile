FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY migrations/ migrations/

RUN uv pip install --system .

EXPOSE 8000

ENV FASTMCP_STATELESS_HTTP=true

RUN adduser --disabled-password --gecos "" appuser
USER appuser

CMD ["uvicorn", "tastebuds.main:app", "--host", "0.0.0.0", "--port", "8000"]
