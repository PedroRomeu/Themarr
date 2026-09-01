import os
import sys
import json

def get_base_path():
    if getattr(sys, 'frozen', False):
        # Running as .exe (compiled by PyInstaller)
        return os.path.dirname(sys.executable)
    # Running as script
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
APP_ROOT_DIR = get_base_path()

if getattr(sys, 'frozen', False):
    FFMPEG_PATH = os.path.join(APP_ROOT_DIR, '_internal', 'bin', 'ffmpeg.exe')
else:
    FFMPEG_PATH = os.path.join(APP_ROOT_DIR, 'bin', 'ffmpeg.exe')

# User profile config folder
USER_HOME = os.path.expanduser('~')
CONFIG_FOLDER = os.path.join(USER_HOME, '.themarr_manager')
os.makedirs(CONFIG_FOLDER, exist_ok=True) 

CONFIG_FILE = os.path.join(CONFIG_FOLDER, 'config.json')

# ==========================================
# SETTINGS MANAGER
# ==========================================
def load_config():
    default_config = {
        "lufs": "-24", 
        "jelly_check": False, 
        "jelly_url": "", 
        "jelly_api": "",
        "open_browser": True,
        "audio_fx": {
            "enabled": False, 
            "remove_silence": False, 
            "fade_in": 0, 
            "fade_out": 0
        }
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key in data:
                    if key in default_config:
                        default_config[key] = data[key]
        except Exception as e:
            print(f"[CONFIG] Error loading settings: {e}")
            
    return default_config

def save_config(data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[CONFIG] Error saving settings: {e}")
