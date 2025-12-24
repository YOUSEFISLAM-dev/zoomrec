#!/bin/bash
# ZoomRec Installation Script for Linux (No GUI)
# Run with: sudo bash install.sh

set -e

echo "============================================"
echo "    ZoomRec Installation Script"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo bash install.sh)"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VERSION=$VERSION_ID
else
    echo "Cannot detect OS. Please install manually."
    exit 1
fi

echo "Detected OS: $OS $VERSION"
echo ""

# Update package manager
echo "Updating package manager..."
if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    apt-get update
elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ] || [ "$OS" = "fedora" ]; then
    if command -v dnf &> /dev/null; then
        dnf check-update || true
    else
        yum check-update || true
    fi
fi

# Install system dependencies
echo ""
echo "Installing system dependencies..."
if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        xvfb \
        pulseaudio \
        pulseaudio-utils \
        ffmpeg \
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
        xdg-utils

elif [ "$OS" = "centos" ] || [ "$OS" = "rhel" ] || [ "$OS" = "fedora" ]; then
    if command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
    else
        PKG_MANAGER="yum"
    fi
    
    $PKG_MANAGER install -y \
        python3 \
        python3-pip \
        xorg-x11-server-Xvfb \
        pulseaudio \
        pulseaudio-utils \
        ffmpeg \
        wget \
        gnupg2 \
        ca-certificates \
        liberation-fonts \
        alsa-lib \
        atk \
        at-spi2-atk \
        cups-libs \
        dbus-libs \
        libdrm \
        mesa-libgbm \
        gtk3 \
        nspr \
        nss \
        libXcomposite \
        libXdamage \
        libXfixes \
        libxkbcommon \
        libXrandr
fi

# Create virtual environment
echo ""
echo "Setting up Python virtual environment..."
INSTALL_DIR="/opt/zoomrec"
mkdir -p $INSTALL_DIR

# Copy application files
cp -r . $INSTALL_DIR/
cd $INSTALL_DIR

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright and browsers
echo ""
echo "Installing Playwright and Chromium..."
playwright install chromium
playwright install-deps chromium

# Create directories
mkdir -p $INSTALL_DIR/recordings
mkdir -p $INSTALL_DIR/instance
mkdir -p /var/log/zoomrec

# Create systemd service
echo ""
echo "Creating systemd service..."
cat > /etc/systemd/system/zoomrec.service << 'EOF'
[Unit]
Description=ZoomRec Meeting Recording Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/zoomrec
Environment=DISPLAY=:99
Environment=RECORDINGS_DIR=/opt/zoomrec/recordings
Environment=DATABASE_URL=sqlite:////opt/zoomrec/instance/zoomrec.db
Environment=SECRET_KEY=change-this-secret-key
Environment=PORT=5000

ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac &
ExecStartPre=/bin/sleep 2
ExecStart=/opt/zoomrec/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 0 run:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create Xvfb service
cat > /etc/systemd/system/xvfb.service << 'EOF'
[Unit]
Description=X Virtual Frame Buffer Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable and start services
echo ""
echo "Starting services..."
systemctl enable xvfb
systemctl start xvfb || true

systemctl enable zoomrec
systemctl start zoomrec

# Print status
echo ""
echo "============================================"
echo "    Installation Complete!"
echo "============================================"
echo ""
echo "ZoomRec is now running on: http://localhost:5000"
echo ""
echo "Commands:"
echo "  - Start:   sudo systemctl start zoomrec"
echo "  - Stop:    sudo systemctl stop zoomrec"
echo "  - Restart: sudo systemctl restart zoomrec"
echo "  - Status:  sudo systemctl status zoomrec"
echo "  - Logs:    sudo journalctl -u zoomrec -f"
echo ""
echo "Recordings are saved to: /opt/zoomrec/recordings"
echo ""
echo "NOTE: Update SECRET_KEY in /etc/systemd/system/zoomrec.service"
echo "      then run: sudo systemctl daemon-reload && sudo systemctl restart zoomrec"
echo ""
