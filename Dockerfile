FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=7860 \
    XDG_CACHE_HOME=/tmp/.cache \
    TMPDIR=/tmp

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" --uid 1000 appuser
USER 1000

EXPOSE 7860

CMD ["uvicorn", "crypto_probability_engine.api.app:app", "--host", "0.0.0.0", "--port", "7860"]

