"""
Flask routes for ZoomRec web application.
"""

from flask import Blueprint, render_template, request, jsonify, send_file, current_app, redirect, url_for
from app import db
from app.models import Recording
from app.recorder import RecordingManager
from datetime import datetime
import os
import re

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

# Global recording manager
recording_manager = None


def get_recording_manager():
    """Get or create recording manager instance."""
    global recording_manager
    if recording_manager is None:
        recording_manager = RecordingManager(
            recordings_dir=current_app.config['RECORDINGS_DIR'],
            max_concurrent=current_app.config['MAX_CONCURRENT_RECORDINGS']
        )
    return recording_manager


# ============== Web Routes ==============

@main_bp.route('/')
def index():
    """Main dashboard page."""
    recordings = Recording.query.order_by(Recording.created_at.desc()).limit(50).all()
    active_count = Recording.query.filter(Recording.status.in_(['pending', 'joining', 'recording'])).count()
    completed_count = Recording.query.filter_by(status='completed').count()
    return render_template('index.html', 
                         recordings=recordings,
                         active_count=active_count,
                         completed_count=completed_count)


@main_bp.route('/recording/<int:recording_id>')
def recording_detail(recording_id):
    """Recording detail page."""
    recording = Recording.query.get_or_404(recording_id)
    return render_template('detail.html', recording=recording)


@main_bp.route('/search')
def search():
    """Search recordings by URL."""
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('main.index'))
    
    # Search by URL or meeting ID
    recordings = Recording.query.filter(
        db.or_(
            Recording.meeting_url.ilike(f'%{query}%'),
            Recording.meeting_id.ilike(f'%{query}%'),
            Recording.meeting_url_hash.ilike(f'%{query}%')
        )
    ).order_by(Recording.created_at.desc()).all()
    
    return render_template('search.html', recordings=recordings, query=query)


@main_bp.route('/download/<int:recording_id>')
def download_recording(recording_id):
    """Download a recording file."""
    recording = Recording.query.get_or_404(recording_id)
    
    if not recording.file_path or not os.path.exists(recording.file_path):
        return "Recording file not found", 404
    
    return send_file(
        recording.file_path,
        as_attachment=True,
        download_name=recording.filename or f'recording_{recording_id}.mp4'
    )


# ============== API Routes ==============

@api_bp.route('/recordings', methods=['GET'])
def list_recordings():
    """List all recordings."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    
    query = Recording.query
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(Recording.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'recordings': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })


@api_bp.route('/recordings', methods=['POST'])
def start_recording():
    """Start a new recording."""
    data = request.get_json() or {}
    meeting_url = data.get('meeting_url', '').strip()
    display_name = data.get('display_name', 'ZoomRec Bot').strip()
    
    if not meeting_url:
        return jsonify({'error': 'meeting_url is required'}), 400
    
    # Validate URL format
    if not is_valid_zoom_url(meeting_url):
        return jsonify({'error': 'Invalid Zoom meeting URL'}), 400
    
    # Extract meeting ID and password from URL
    meeting_id, password = parse_zoom_url(meeting_url)
    
    # Check concurrent recording limit
    active_count = Recording.query.filter(
        Recording.status.in_(['pending', 'joining', 'recording'])
    ).count()
    
    if active_count >= current_app.config['MAX_CONCURRENT_RECORDINGS']:
        return jsonify({'error': 'Maximum concurrent recordings limit reached'}), 429
    
    # Create recording entry
    recording = Recording(
        meeting_url=meeting_url,
        meeting_id=meeting_id,
        meeting_password=password,
        display_name=display_name,
        status='pending'
    )
    db.session.add(recording)
    db.session.commit()
    
    # Start recording in background
    manager = get_recording_manager()
    manager.start_recording(recording.id)
    
    return jsonify(recording.to_dict()), 201


@api_bp.route('/recordings/<int:recording_id>', methods=['GET'])
def get_recording(recording_id):
    """Get recording details."""
    recording = Recording.query.get_or_404(recording_id)
    return jsonify(recording.to_dict())


@api_bp.route('/recordings/<int:recording_id>/stop', methods=['POST'])
def stop_recording(recording_id):
    """Stop an active recording."""
    recording = Recording.query.get_or_404(recording_id)
    
    if recording.status not in ['pending', 'joining', 'recording']:
        return jsonify({'error': 'Recording is not active'}), 400
    
    manager = get_recording_manager()
    success = manager.stop_recording(recording_id)
    
    if success:
        return jsonify({'message': 'Recording stopped', 'recording': recording.to_dict()})
    else:
        return jsonify({'error': 'Failed to stop recording'}), 500


@api_bp.route('/recordings/<int:recording_id>/stop-leave', methods=['POST'])
def stop_and_leave_recording(recording_id):
    """Stop recording and leave meeting immediately."""
    recording = Recording.query.get_or_404(recording_id)

    if recording.status not in ['pending', 'joining', 'recording']:
        return jsonify({'error': 'Recording is not active'}), 400

    manager = get_recording_manager()
    success = manager.stop_and_leave(recording_id)

    if success:
        return jsonify({'message': 'Recording stopped and left', 'recording': recording.to_dict()})
    else:
        return jsonify({'error': 'Failed to stop recording'}), 500


@api_bp.route('/recordings/<int:recording_id>', methods=['DELETE'])
def delete_recording(recording_id):
    """Delete a recording."""
    recording = Recording.query.get_or_404(recording_id)
    
    # Stop if still recording
    if recording.status in ['pending', 'joining', 'recording']:
        manager = get_recording_manager()
        manager.stop_recording(recording_id)
    
    # Delete file if exists
    if recording.file_path and os.path.exists(recording.file_path):
        try:
            os.remove(recording.file_path)
        except Exception:
            pass
    
    db.session.delete(recording)
    db.session.commit()
    
    return jsonify({'message': 'Recording deleted'})


@api_bp.route('/recordings/search', methods=['GET'])
def api_search():
    """Search recordings by URL."""
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'recordings': [], 'query': query})
    
    recordings = Recording.query.filter(
        db.or_(
            Recording.meeting_url.ilike(f'%{query}%'),
            Recording.meeting_id.ilike(f'%{query}%'),
            Recording.meeting_url_hash.ilike(f'%{query}%')
        )
    ).order_by(Recording.created_at.desc()).all()
    
    return jsonify({
        'recordings': [r.to_dict() for r in recordings],
        'query': query,
        'count': len(recordings)
    })


@api_bp.route('/status', methods=['GET'])
def api_status():
    """Get system status."""
    active_recordings = Recording.query.filter(
        Recording.status.in_(['pending', 'joining', 'recording'])
    ).count()
    
    return jsonify({
        'status': 'running',
        'active_recordings': active_recordings,
        'max_concurrent': current_app.config['MAX_CONCURRENT_RECORDINGS'],
        'recordings_dir': current_app.config['RECORDINGS_DIR']
    })


# ============== Helper Functions ==============

def is_valid_zoom_url(url):
    """Validate Zoom meeting URL format."""
    patterns = [
        r'https?://[\w.-]*zoom\.us/j/\d+',
        r'https?://[\w.-]*zoom\.us/my/[\w.-]+',
        r'https?://[\w.-]*zoom\.us/wc/\d+',
    ]
    return any(re.match(pattern, url) for pattern in patterns)


def parse_zoom_url(url):
    """Extract meeting ID and password from Zoom URL."""
    meeting_id = None
    password = None
    
    # Extract meeting ID
    match = re.search(r'/j/(\d+)', url)
    if match:
        meeting_id = match.group(1)
    
    # Extract password from URL params
    match = re.search(r'[?&]pwd=([^&]+)', url)
    if match:
        password = match.group(1)
    
    return meeting_id, password
