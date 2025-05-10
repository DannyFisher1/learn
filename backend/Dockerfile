FROM python:3.13-slim

# Install build tools and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*




# Set workdir
WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install playwright
RUN playwright install
RUN playwright install-deps
RUN playwright install chromium



CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000", "--reload", "--reload-dir", "/app/app", "--reload-dir", "/app"]