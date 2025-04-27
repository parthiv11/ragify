# Step 1: Use the official MindsDB image from Docker Hub
FROM mindsdb/mindsdb:latest

# Step 2: Install additional dependencies for your custom app (e.g., FastAPI, Streamlit)
# Update and install any system dependencies needed by your application
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    netcat-openbsd 
# Step 3: Set the working directory
WORKDIR /app

# Step 4: Copy the requirements.txt file into the container (if you have one)
COPY requirements.txt /app/

# Step 5: Install Python dependencies (e.g., FastAPI, Streamlit)
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy your application code into the container
COPY . /app

# Step 7: Expose necessary ports
EXPOSE 47334 8000 8501

# Step 8: Copy the wait script into the container
COPY wait_for_mindsdb.sh /app/wait_for_mindsdb.sh
RUN chmod +x /app/wait_for_mindsdb.sh

# Step 9: Run MindsDB, wait for it to be ready, then start FastAPI and Streamlit
CMD ["/bin/bash", "-c", "/app/wait_for_mindsdb.sh && uvicorn app:app --host 0.0.0.0 --port 8000 & streamlit run app.py"]
