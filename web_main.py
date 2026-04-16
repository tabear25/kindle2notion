"""Entry point for the kindle2notion web interface.

Usage:
    python web_main.py

Access from any device on the same network at http://<server-ip>:5000
"""

from web.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
