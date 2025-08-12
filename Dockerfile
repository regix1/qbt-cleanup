FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./

# Create config directory with proper permissions
RUN mkdir -p /config && \
    chmod 777 /config

# Create non-root user
RUN useradd -m -u 1000 qbtuser && \
    chown -R qbtuser:qbtuser /app

# Switch to non-root user
USER qbtuser

ENTRYPOINT ["python", "-u", "main.py"]