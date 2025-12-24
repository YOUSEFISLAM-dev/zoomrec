# ZoomRec - Zoom Meeting Recording Tool

A web application to record Zoom meetings automatically. Simply paste a meeting URL, and the bot will join and record until the meeting ends.

> ⚠️ **Disclaimer**: This tool is provided for educational purposes only. Users are responsible for complying with all applicable laws and terms of service. Always get proper consent before recording any meeting.

## Features

- 🎥 **Automatic Recording** - Join and record Zoom meetings automatically
- 🔍 **Search & Index** - Find recordings by meeting URL or ID
- 🖥️ **Headless Operation** - Runs on Linux servers without GUI
- 📦 **Docker Support** - Easy deployment with Docker
- 🌐 **Web Interface** - Clean, responsive dashboard
- 📡 **REST API** - Programmatic access to all features

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/zoomrec.git
cd zoomrec

# Start with Docker Compose
docker-compose up -d

# Access the web interface
open http://localhost:5000
```

### Option 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/zoomrec.git
cd zoomrec

# Run the installation script (Ubuntu/Debian)
sudo bash install.sh

# Or install manually:
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv xvfb pulseaudio ffmpeg

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium
playwright install-deps chromium

# 5. Start Xvfb (virtual display)
Xvfb :99 -screen 0 1920x1080x24 -ac &
export DISPLAY=:99

# 6. Run the application
python run.py
```

## Usage

### Web Interface

1. Open `http://localhost:5000` in your browser
2. Paste a Zoom meeting URL in the form
3. Click "Start Recording"
4. Monitor the recording status in the dashboard
5. Download recordings when complete

### API Endpoints

#### Start Recording
```bash
curl -X POST http://localhost:5000/api/recordings \
  -H "Content-Type: application/json" \
  -d '{"meeting_url": "https://zoom.us/j/123456789?pwd=xxx", "display_name": "RecBot"}'
```

#### List Recordings
```bash
curl http://localhost:5000/api/recordings
```

#### Search Recordings
```bash
curl "http://localhost:5000/api/recordings/search?q=123456789"
```

#### Get Recording Status
```bash
curl http://localhost:5000/api/recordings/1
```

#### Stop Recording
```bash
curl -X POST http://localhost:5000/api/recordings/1/stop
```

#### Delete Recording
```bash
curl -X DELETE http://localhost:5000/api/recordings/1
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key` | Flask secret key |
| `DATABASE_URL` | `sqlite:///zoomrec.db` | Database connection string |
| `RECORDINGS_DIR` | `./recordings` | Directory to save recordings |
| `MAX_CONCURRENT_RECORDINGS` | `3` | Maximum simultaneous recordings |
| `PORT` | `5000` | Server port |
| `DISPLAY` | `:99` | X display for headless mode |

## Project Structure

```
zoomrec/
├── app/
│   ├── __init__.py         # Flask app factory
│   ├── models.py           # Database models
│   ├── routes.py           # Web & API routes
│   ├── recorder.py         # Recording engine
│   ├── browser_automation.py  # Playwright automation
│   └── templates/          # HTML templates
│       ├── base.html
│       ├── index.html
│       ├── detail.html
│       └── search.html
├── recordings/             # Saved recordings
├── instance/              # SQLite database
├── run.py                 # Application entry point
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose config
├── install.sh            # Installation script
└── README.md
```

## How It Works

1. **Web Interface** - Flask serves a responsive web dashboard
2. **Browser Automation** - Playwright controls a headless Chromium browser
3. **Virtual Display** - Xvfb provides a virtual screen for the browser
4. **Screen Recording** - FFmpeg captures the virtual display and audio
5. **Meeting Detection** - The bot monitors for meeting end signals

## Troubleshooting

### Recording fails to start
- Ensure Xvfb is running: `ps aux | grep Xvfb`
- Check the DISPLAY environment variable
- Verify FFmpeg is installed: `ffmpeg -version`

### Browser won't join meeting
- Meeting may require authentication
- Password might be missing from URL
- Waiting room might be enabled

### No audio in recording
- PulseAudio must be running: `pulseaudio --start`
- Check virtual audio sink is configured

### View logs
```bash
# Docker
docker-compose logs -f

# Systemd
sudo journalctl -u zoomrec -f
```

## System Requirements

- **OS**: Linux (Ubuntu 20.04+, Debian 10+, CentOS 8+)
- **RAM**: 2GB minimum (4GB recommended per concurrent recording)
- **Storage**: Depends on recording duration (~500MB/hour at 720p)
- **CPU**: 2 cores minimum (more for concurrent recordings)

## License

MIT License - Use at your own risk and responsibility.

---

**Note**: This tool is for personal use only. Always respect privacy laws and obtain proper consent before recording any meeting.