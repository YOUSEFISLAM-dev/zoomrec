FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # X11 and virtual display
    xvfb \
    x11vnc \
    xauth \
    # Audio
    pulseaudio \
    pulseaudio-utils \
    alsa-utils \
    # Video recording
    ffmpeg \
    # Browser dependencies
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    # Misc utilities
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY . .

# Create directories
RUN mkdir -p /app/recordings /app/instance

# Set up PulseAudio
RUN mkdir -p /run/pulse && \
    echo "load-module module-null-sink sink_name=virtual_speaker sink_properties=device.description=VirtualSpeaker" >> /etc/pulse/default.pa && \
    echo "set-default-sink virtual_speaker" >> /etc/pulse/default.pa

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Start Xvfb\n\
Xvfb :99 -screen 0 1920x1080x24 -ac &\n\
export DISPLAY=:99\n\
sleep 2\n\
\n\
# Start PulseAudio\n\
pulseaudio --start --exit-idle-time=-1 || true\n\
sleep 1\n\
\n\
# Run the application\n\
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 0 "run:app"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 5000

# Set environment variables
ENV DISPLAY=:99
ENV RECORDINGS_DIR=/app/recordings
ENV DATABASE_URL=sqlite:////app/instance/zoomrec.db

# Run entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
