# Multi-stage lightweight CPU-only container image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install dependencies (CPU-only PyTorch ensures final image is well under 2GB limit)
COPY service/requirements.txt /app/service/requirements.txt
RUN pip install --no-cache-dir -r /app/service/requirements.txt

# Copy application code and schema (NO MODEL WEIGHTS INCLUDED)
COPY service/app.py /app/service/app.py
COPY data/schema.json /app/data/schema.json

EXPOSE 8000

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]

