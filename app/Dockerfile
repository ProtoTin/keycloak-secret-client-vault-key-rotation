FROM python:3.9-slim

WORKDIR /app

# Install curl for debugging
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files from app directory
COPY app/ .

# Create scripts directory and copy scripts
RUN mkdir -p /app/scripts
COPY scripts/* /app/scripts/

CMD ["python", "app.py"] 