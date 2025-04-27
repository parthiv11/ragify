# Use the official Python base image
FROM python:3.10-slim

# Install system dependencies and tools for checking network connection
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
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

# Make the wait script executable
RUN chmod +x /app/wait_for_mindsdb.sh

# Expose the necessary ports for MindsDB, FastAPI, and Streamlit
EXPOSE 47334 8000 8501

# Start MindsDB in the background
RUN python -m mindsdb &

# Run the script that waits for MindsDB and then starts FastAPI and Streamlit
CMD ["/app/wait_for_mindsdb.sh"]
