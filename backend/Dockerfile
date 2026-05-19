FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY backend /app/backend
COPY src /app/src
COPY config /app/config

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 9527

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9527"]
