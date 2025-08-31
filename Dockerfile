FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src/ ./src/

# Create config directory
RUN mkdir -p /config

# Create entrypoint script that handles permissions
RUN echo '#!/bin/sh\n\
if [ ! -z "$PUID" ] && [ ! -z "$PGID" ]; then\n\
    echo "Setting ownership to $PUID:$PGID"\n\
    chown -R $PUID:$PGID /config\n\
fi\n\
exec python -u -m src.qbt_cleanup.main "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]