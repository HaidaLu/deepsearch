FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create storage directory for uploaded files
RUN mkdir -p /app/storage/files

EXPOSE 8000

CMD ["uvicorn", "app_main:app", "--host", "0.0.0.0", "--port", "8000"]
