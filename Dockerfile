FROM python:3.11-slim

WORKDIR /app

# Install git for cloning MindsDB
RUN apt-get update && apt-get install -y git

# Clone MindsDB repository
RUN git clone https://github.com/parthiv11/mindsdb.git

RUN pip install -e mindsdb

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY main.py .


# Expose ports
EXPOSE 8000 8501 47334

# Set default environment variables
ENV API_PORT=8000
ENV STREAMLIT_PORT=8501
ENV MINDSDB_HOST=mindsdb
ENV MINDSDB_PORT=47334

# Create startup script
RUN echo '#!/bin/bash\n\
cd mindsdb && python -m mindsdb &\n\
uvicorn main:app --host 0.0.0.0 --port $API_PORT &\n\
streamlit run app.py --server.port $STREAMLIT_PORT --server.address 0.0.0.0\n\
' > /app/start.sh && chmod +x /app/start.sh

# Start application
CMD ["/app/start.sh"]