import sys
import socket
import logging
import threading
import webview
from flask import Flask

from api_controller import Api
from core.logger import LogRedirector
from routes import register_routes

# Initialize Flask
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Initialize API System
api_system = Api()

# Register Flask Routes
register_routes(app, api_system)

# Start Server
def start_server():
    app.run(host='127.0.0.1', port=5000, debug=False)

def is_app_running():
    """Tries to connect to port 5000. If successful, Themarr is already running."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', 5000)) == 0

def start_flask_background():
    if is_app_running():
        print("An instance of Themarr is already running. Closing this new attempt...")
        sys.exit(0)

    sys.stdout = LogRedirector(sys.__stdout__)
    sys.stderr = sys.stdout
    
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()

if __name__ == '__main__':
    
    start_flask_background()
    
    window = webview.create_window(
        "Themarr Manager", 
        "http://127.0.0.1:5000", 
        js_api=api_system,
        width=900, 
        height=750, 
        background_color='#1e1e1e'
    )
    
    webview.start()
    sys.exit()