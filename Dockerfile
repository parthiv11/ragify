FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make wait script executable
RUN chmod +x wait_for_mindsdb.sh

# Expose ports
EXPOSE 8000 8501

# Set default environment variables
ENV API_PORT=8000
ENV STREAMLIT_PORT=8501
ENV MINDSDB_HOST=mindsdb
ENV MINDSDB_PORT=47334

# Start application
CMD ["./wait_for_mindsdb.sh"]