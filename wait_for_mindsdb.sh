#!/bin/bash

# Function to check if MindsDB is up
wait_for_mindsdb() {
    while ! nc -z localhost 47334; do
        echo "Waiting for MindsDB to start..."
        sleep 1
    done
    echo "MindsDB is up!"
}

# Call the function
wait_for_mindsdb

# Start FastAPI and Streamlit once MindsDB is up
uvicorn app:app --host 0.0.0.0 --port 8000 & 
streamlit run app.py 
