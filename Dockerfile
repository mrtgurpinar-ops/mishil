# Production Dockerfile for Mishil Backend
FROM python:3.11-slim

# System dependencies for librosa & soundfile (libsndfile1, ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_NAME=mishil

EXPOSE 8080

# Run via python main.py for resilient port parsing
CMD ["python", "app/main.py"]
