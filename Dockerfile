# Use the official Python base image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    netcat \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements.txt and install the dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY . /app

# Copy the wait script into the container
COPY wait_for_mindsdb.sh /app/wait_for_mindsdb.sh
RUN chmod +x /app/wait_for_mindsdb.sh

# Expose the necessary ports
EXPOSE 47334 8000 8501

# Run the script that waits for MindsDB and then starts FastAPI and Streamlit
CMD ["/app/wait_for_mindsdb.sh"]
