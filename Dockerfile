FROM python:3.11-slim

# Force Python to print errors immediately so they show up in Render logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system libraries required by curl_cffi for browser impersonation
RUN apt-get update && apt-get install -y \
    libnss3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render provides the PORT environment variable dynamically.
# We use the shell form of CMD to read it.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}