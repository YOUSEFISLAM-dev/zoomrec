"""
Recording engine for ZoomRec.
Uses Playwright for headless browser automation and FFmpeg for recording.
"""

import os
import signal
import subprocess
import threading
import time
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecordingManager:
    """Manages recording sessions."""
    
    def __init__(self, recordings_dir, max_concurrent=3):
        self.recordings_dir = recordings_dir
        self.max_concurrent = max_concurrent
        self.active_recordings = {}  # recording_id -> RecordingSession
        self._lock = threading.Lock()
        
        os.makedirs(recordings_dir, exist_ok=True)
    
    def start_recording(self, recording_id):
        """Start a new recording in a background thread."""
        thread = threading.Thread(
            target=self._run_recording,
            args=(recording_id,),
            daemon=True
        )
        thread.start()
        return True
    
    def _run_recording(self, recording_id):
        """Run the recording process."""
        from app import db, create_app
        from app.models import Recording
        
        app = create_app()
        with app.app_context():
            recording = Recording.query.get(recording_id)
            if not recording:
                logger.error(f"Recording {recording_id} not found")
                return
            
            session = RecordingSession(
                recording_id=recording_id,
                meeting_url=recording.meeting_url,
                display_name=recording.display_name,
                recordings_dir=self.recordings_dir
            )
            
            with self._lock:
                self.active_recordings[recording_id] = session
            
            try:
                # Update status
                recording.status = 'joining'
                db.session.commit()
                
                # Start recording
                success = session.start()
                
                if success:
                    recording.status = 'recording'
                    recording.started_at = datetime.utcnow()
                    recording.pid = session.pid
                    db.session.commit()
                    
                    # Wait for recording to complete
                    session.wait()
                    
                    # Update final status
                    recording = Recording.query.get(recording_id)
                    recording.status = 'completed'
                    recording.ended_at = datetime.utcnow()
                    recording.file_path = session.output_path
                    recording.filename = os.path.basename(session.output_path)
                    
                    if os.path.exists(session.output_path):
                        recording.file_size = os.path.getsize(session.output_path)
                        recording.duration_seconds = session.get_duration()
                    
                    db.session.commit()
                else:
                    recording.status = 'failed'
                    recording.error_message = session.error_message or 'Failed to start recording'
                    db.session.commit()
                    
            except Exception as e:
                logger.exception(f"Recording {recording_id} failed")
                recording = Recording.query.get(recording_id)
                recording.status = 'failed'
                recording.error_message = str(e)
                db.session.commit()
            finally:
                with self._lock:
                    self.active_recordings.pop(recording_id, None)
    
    def stop_recording(self, recording_id, leave_first=False):
        """Stop an active recording. If leave_first, kill browser immediately to exit meeting."""
        from app import db, create_app
        from app.models import Recording

        with self._lock:
            session = self.active_recordings.get(recording_id)

        if session:
            session.stop(leave_first=leave_first)

            app = create_app()
            with app.app_context():
                recording = Recording.query.get(recording_id)
                if recording:
                    recording.status = 'stopped'
                    recording.ended_at = datetime.utcnow()
                    if session.output_path and os.path.exists(session.output_path):
                        recording.file_path = session.output_path
                        recording.filename = os.path.basename(session.output_path)
                        recording.file_size = os.path.getsize(session.output_path)
                        recording.duration_seconds = session.get_duration()
                    db.session.commit()
            return True
        return False

    def stop_and_leave(self, recording_id):
        """Stop recording and leave meeting immediately (browser-first)."""
        return self.stop_recording(recording_id, leave_first=True)
    
    def get_active_count(self):
        """Get number of active recordings."""
        with self._lock:
            return len(self.active_recordings)


class RecordingSession:
    """Handles a single recording session using Playwright and FFmpeg."""
    
    def __init__(self, recording_id, meeting_url, display_name, recordings_dir):
        self.recording_id = recording_id
        self.meeting_url = meeting_url
        self.display_name = display_name
        self.recordings_dir = recordings_dir
        
        self.browser_process = None
        self.ffmpeg_process = None
        self.pid = None
        self.error_message = None
        self.start_time = None
        self.end_time = None
        
        # Generate output filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        meeting_id = self._extract_meeting_id() or 'unknown'
        self.output_filename = f"zoom_{meeting_id}_{timestamp}.mp4"
        self.output_path = os.path.join(recordings_dir, self.output_filename)
        
        # Virtual display settings
        self.display_num = 99 + recording_id % 100
        self.screen_width = 1920
        self.screen_height = 1080
    
    def _extract_meeting_id(self):
        """Extract meeting ID from URL."""
        match = re.search(r'/j/(\d+)', self.meeting_url)
        return match.group(1) if match else None
    
    def start(self):
        """Start the recording session."""
        try:
            self.start_time = datetime.now()
            
            # Start virtual display (Xvfb)
            self._start_virtual_display()
            
            # Start PulseAudio virtual audio
            self._start_audio()
            
            # Start browser and join meeting
            self._start_browser()
            
            # Wait for meeting to load
            time.sleep(10)
            
            # Start FFmpeg recording
            self._start_ffmpeg()
            
            if self.ffmpeg_process:
                self.pid = self.ffmpeg_process.pid
                return True
            
            return False
            
        except Exception as e:
            logger.exception("Failed to start recording session")
            self.error_message = str(e)
            self.stop()
            return False
    
    def _start_virtual_display(self):
        """Start Xvfb virtual display."""
        display = f":{self.display_num}"
        
        # Kill any existing Xvfb on this display
        subprocess.run(
            ['/usr/bin/pkill', '-f', f'Xvfb {display}'],
            capture_output=True
        )
        time.sleep(0.5)
        
        # Start Xvfb
        self.xvfb_process = subprocess.Popen(
            [
                '/usr/bin/Xvfb', display,
                '-screen', '0', f'{self.screen_width}x{self.screen_height}x24',
                '-ac'
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        
        os.environ['DISPLAY'] = display
        time.sleep(1)
        logger.info(f"Started Xvfb on display {display}")
    
    def _start_audio(self):
        """Start PulseAudio for audio capture."""
        # Create a virtual audio sink
        subprocess.run(
            ['/usr/bin/pulseaudio', '--start', '--exit-idle-time=-1'],
            capture_output=True,
            env={**os.environ, 'DISPLAY': f':{self.display_num}'}
        )
        
        # Load virtual sink for recording
        subprocess.run(
            ['/usr/bin/pactl', 'load-module', 'module-null-sink', 
             f'sink_name=recording_{self.recording_id}'],
            capture_output=True
        )
        logger.info("Started PulseAudio")
    
    def _start_browser(self):
        """Start browser and join Zoom meeting using Playwright."""
        script_path = os.path.join(os.path.dirname(__file__), 'browser_automation.py')
        
        env = os.environ.copy()
        env['DISPLAY'] = f':{self.display_num}'
        env['MEETING_URL'] = self.meeting_url
        env['DISPLAY_NAME'] = self.display_name
        env['RECORDING_ID'] = str(self.recording_id)
        
        self.browser_process = subprocess.Popen(
            ['python3', script_path],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # isolate process group so we can kill fast
        )
        logger.info(f"Started browser automation for meeting: {self.meeting_url}")
    
    def _start_ffmpeg(self):
        """Start FFmpeg to record the screen and audio."""
        display = f':{self.display_num}'
        
        ffmpeg_cmd = [
            '/usr/bin/ffmpeg',
            '-y',  # Overwrite output
            '-f', 'x11grab',  # X11 screen capture
            '-video_size', f'{self.screen_width}x{self.screen_height}',
            '-framerate', '30',
            '-i', f'{display}.0',  # Display input
            '-f', 'pulse',  # PulseAudio input
            '-i', 'default',  # Default audio device
            '-c:v', 'libx264',  # H.264 video codec
            '-preset', 'ultrafast',  # Fast encoding
            '-crf', '23',  # Quality (lower = better)
            '-c:a', 'aac',  # AAC audio codec
            '-b:a', '128k',  # Audio bitrate
            '-pix_fmt', 'yuv420p',  # Pixel format for compatibility
            self.output_path
        ]
        
        self.ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid  # isolate process group for fast teardown
        )
        logger.info(f"Started FFmpeg recording to {self.output_path}")
    
    def wait(self):
        """Wait for the recording to complete (meeting ends)."""
        if self.browser_process:
            # Wait for browser to exit (meeting ended or kicked)
            self.browser_process.wait()
        
        # Give a small buffer before stopping FFmpeg
        time.sleep(2)
        self.stop()
    
    def stop(self, leave_first=False):
        """Stop all recording processes. If leave_first, kill browser first to exit meeting immediately."""
        self.end_time = datetime.now()

        def _kill_process_group(proc, timeout_terminate=2, timeout_kill=1):
            if not proc or proc.poll() is not None:
                return
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=timeout_terminate)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                try:
                    proc.wait(timeout=timeout_kill)
                except Exception:
                    pass

        if leave_first:
            _kill_process_group(self.browser_process, timeout_terminate=1, timeout_kill=1)

        # Stop FFmpeg
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                self.ffmpeg_process.stdin.write(b'q')
                self.ffmpeg_process.stdin.flush()
                self.ffmpeg_process.wait(timeout=4)
            except Exception:
                _kill_process_group(self.ffmpeg_process)

        # Stop browser (if not already)
        if not leave_first:
            _kill_process_group(self.browser_process, timeout_terminate=2, timeout_kill=1)

        # Stop Xvfb
        if hasattr(self, 'xvfb_process') and self.xvfb_process:
            _kill_process_group(self.xvfb_process, timeout_terminate=1, timeout_kill=1)

        logger.info(f"Stopped recording session {self.recording_id}")
    
    def get_duration(self):
        """Get recording duration in seconds."""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        
        # Try to get duration from file using ffprobe
        if os.path.exists(self.output_path):
            try:
                result = subprocess.run(
                    [
                        'ffprobe', '-v', 'quiet',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        self.output_path
                    ],
                    capture_output=True,
                    text=True
                )
                return int(float(result.stdout.strip()))
            except Exception:
                pass
        return None
