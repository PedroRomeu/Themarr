"""Headless entry point for Docker: web server with login, no desktop window or tray icon"""
import sys

from core.config import SERVER_MODE, SERVER_HOST, SERVER_PORT, MEDIA_ROOT
from core.logger import LogRedirector

if __name__ == '__main__':
    if not SERVER_MODE:
        # Without server mode there is no login and no media guard: refuse to listen on the network
        sys.exit("Themarr_Docker.py requires THEMARR_MODE=server.")

    sys.stdout = LogRedirector(sys.__stdout__)
    sys.stderr = sys.stdout

    from waitress import serve
    from main import app

    print(f"[SERVER] Themarr listening on {SERVER_HOST}:{SERVER_PORT} | media root: {MEDIA_ROOT}")
    serve(app, host=SERVER_HOST, port=SERVER_PORT, threads=8)
