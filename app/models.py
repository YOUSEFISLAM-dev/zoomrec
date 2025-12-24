"""
Database models for ZoomRec.
"""

from datetime import datetime
from app import db
import hashlib


class Recording(db.Model):
    """Model for storing meeting recording information."""
    
    __tablename__ = 'recordings'
    
    id = db.Column(db.Integer, primary_key=True)
    meeting_url = db.Column(db.String(500), nullable=False, index=True)
    meeting_url_hash = db.Column(db.String(64), unique=False, index=True)
    meeting_id = db.Column(db.String(100), nullable=True)
    meeting_password = db.Column(db.String(100), nullable=True)
    display_name = db.Column(db.String(100), default='ZoomRec Bot')
    
    # Recording status
    status = db.Column(db.String(50), default='pending')  # pending, joining, recording, completed, failed, stopped
    error_message = db.Column(db.Text, nullable=True)
    
    # File information
    filename = db.Column(db.String(500), nullable=True)
    file_path = db.Column(db.String(1000), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    
    # Process tracking
    pid = db.Column(db.Integer, nullable=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.meeting_url:
            self.meeting_url_hash = self._hash_url(self.meeting_url)
    
    @staticmethod
    def _hash_url(url):
        """Create a hash of the meeting URL for indexing."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    
    @property
    def duration_formatted(self):
        """Return formatted duration string."""
        if not self.duration_seconds:
            return "N/A"
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    
    @property
    def file_size_formatted(self):
        """Return formatted file size string."""
        if not self.file_size:
            return "N/A"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024
        return f"{self.file_size:.1f} TB"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'meeting_url': self.meeting_url,
            'meeting_id': self.meeting_id,
            'display_name': self.display_name,
            'status': self.status,
            'error_message': self.error_message,
            'filename': self.filename,
            'file_size': self.file_size,
            'file_size_formatted': self.file_size_formatted,
            'duration_seconds': self.duration_seconds,
            'duration_formatted': self.duration_formatted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }
    
    def __repr__(self):
        return f'<Recording {self.id}: {self.meeting_url[:50]}... [{self.status}]>'


class Settings(db.Model):
    """Application settings."""
    
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    
    @classmethod
    def get(cls, key, default=None):
        """Get a setting value."""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @classmethod
    def set(cls, key, value):
        """Set a setting value."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
