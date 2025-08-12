FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./

# Create config directory
RUN mkdir -p /config

# Run as non-root user
RUN useradd -m -u 1000 qbtuser && \
    chown -R qbtuser:qbtuser /app /config
USER qbtuser

ENTRYPOINT ["python", "-u", "main.py"]