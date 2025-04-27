#!/bin/bash

echo "Waiting for MindsDB to be ready..."
while ! nc -z $MINDSDB_HOST $MINDSDB_PORT; do
  sleep 1
done
echo "MindsDB is ready!"

# Start FastAPI server in the background
uvicorn main:app --host 0.0.0.0 --port $API_PORT &

# Start Streamlit app
streamlit run app.py --server.port $STREAMLIT_PORT --server.address 0.0.0.0
