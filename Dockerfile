# Stage 1: Build Angular
FROM node:20-slim AS angular-build
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npx ng build --configuration=production

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY --from=angular-build /web/dist/web/browser /app/web/

RUN mkdir -p /config

# Create entrypoint script
RUN echo '#!/bin/sh\n\
if [ ! -z "$PUID" ] && [ ! -z "$PGID" ]; then\n\
    echo "Setting ownership to $PUID:$PGID"\n\
    chown -R $PUID:$PGID /config\n\
fi\n\
exec python -u -m src.qbt_cleanup.main "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Create control script
RUN echo '#!/bin/sh\n\
exec python -u -m src.qbt_cleanup.ctl "$@"' > /usr/local/bin/qbt-cleanup-ctl && \
    chmod +x /usr/local/bin/qbt-cleanup-ctl

EXPOSE 9999
ENTRYPOINT ["/entrypoint.sh"]
