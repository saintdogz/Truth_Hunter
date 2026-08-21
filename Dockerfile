FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system truthhunter \
    && adduser --system --ingroup truthhunter --home /app truthhunter

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER truthhunter

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

