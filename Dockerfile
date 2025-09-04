# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . .

# Flask app listens on 8000 via gunicorn
EXPOSE 8000

# run as non-root (good practice)
RUN useradd -m appuser
USER appuser

CMD ["gunicorn", "-w", "2", "-k", "gthread", "-b", "0.0.0.0:8000", "app:app"]

