#!/usr/bin/env python3
"""
Main entry point for ZoomRec application.
"""

from app import create_app

app = create_app()

if __name__ == '__main__':
    import os
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"Starting ZoomRec server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
