import os
import sys
import json
import queue
import socket
import logging
import re
import tempfile
import threading
import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog
import requests
import yt_dlp
import webview
from flask import Flask, render_template, jsonify, request
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error, TIT2, TALB, TCON

# ==========================================
# PATH CONFIGURATIONS & GLOBALS
# ==========================================
def get_base_path():
    if getattr(sys, 'frozen', False):
        # Running as .exe (compiled by PyInstaller)
        return os.path.dirname(sys.executable)
    # Running as script
    return os.path.dirname(os.path.abspath(__file__))
    
APP_ROOT_DIR = get_base_path()
FFMPEG_PATH = os.path.join(APP_ROOT_DIR, 'bin', 'ffmpeg.exe')

# User profile config folder
USER_HOME = os.path.expanduser('~')
CONFIG_FOLDER = os.path.join(USER_HOME, '.themarr_manager')
os.makedirs(CONFIG_FOLDER, exist_ok=True) 

CONFIG_FILE = os.path.join(CONFIG_FOLDER, 'config.json')

# Initialize Flask
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Mute default Flask logs

# ==========================================
# LOGGING ENGINE
# ==========================================
log_queue = queue.Queue()

class LogRedirector:
    def __init__(self, original_terminal):
        self.terminal = original_terminal
        self.capture = True

    def write(self, text):
        if self.terminal:
            self.terminal.write(text)
            self.terminal.flush()
        
        if self.capture:
            clean_text = text.replace('\r', '\n')
            if clean_text:
                log_queue.put(clean_text)

    def flush(self):
        if self.terminal:
            self.terminal.flush()

# ==========================================
# SETTINGS MANAGER
# ==========================================
def load_config():
    default_config = {
        "lufs": "-24", 
        "jelly_check": False, 
        "jelly_url": "", 
        "jelly_api": "",
        "open_browser": True
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

# ==========================================
# CORE UTILITIES (FFMPEG & FILE MANAGEMENT)
# ==========================================
def normalize_audio_ffmpeg(mp3_path, target_lufs):
    """
    Runs FFmpeg to normalize audio, imitating the safe logic from the old .bat file.
    """
    temp_file = mp3_path + ".temp.mp3"
    
    command = [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error", "-y",
        "-i", mp3_path,
        "-filter:a", f"loudnorm=I={target_lufs}:LRA=11:TP=-1.0",
        "-b:a", "320k",
        temp_file
    ]
    
    try:
        # Run without opening black command windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        subprocess.run(command, check=True, startupinfo=startupinfo)
        
        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
            shutil.move(temp_file, mp3_path)
            return True
        else:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False
    except Exception as e:
        print(f"[FFMPEG] ❌ Error normalizing {mp3_path}: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def download_music(youtube_url):
    print(f"\n[DOWNLOAD] Starting download: {youtube_url}")
    
    os_temp_folder = tempfile.gettempdir() 
    
    options = {
        'format': 'bestaudio/best',
        'ffmpeg_location': FFMPEG_PATH,
        'extractor_args': {'youtube': {'client': ['android']}},
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        'outtmpl': os.path.join(os_temp_folder, '%(title)s.%(ext)s'),
        'nocolor': True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(youtube_url, download=True)
        base_filename = ydl.prepare_filename(info)
        mp3_file = os.path.splitext(base_filename)[0] + '.mp3'
    return mp3_file

def generate_destination_path(anime_folder, theme_type, custom_name, season_folder=None, multiple_main=False):
    if not custom_name.endswith('.mp3'):
        custom_name += '.mp3'
        
    if theme_type == 'temporada' or theme_type == 'season':
        final_folder = os.path.join(anime_folder, season_folder, 'theme-music')
        final_file = os.path.join(final_folder, custom_name)
    elif theme_type == 'main':
        theme_music_folder = os.path.join(anime_folder, 'theme-music')
        loose_theme_file = os.path.join(anime_folder, 'theme.mp3')
        
        # CASO 1: É múltiplo na fila de agora OU a pasta 'theme-music' já existe no disco
        if multiple_main or os.path.isdir(theme_music_folder):
            final_folder = theme_music_folder
            final_file = os.path.join(final_folder, custom_name)
            
        # CASO 2: A pasta não existe, mas existe um ficheiro 'theme.mp3' solto de um download anterior
        elif os.path.exists(loose_theme_file):
            os.makedirs(theme_music_folder, exist_ok=True)
            # Arrasta o ficheiro solto antigo para a nova pasta 'theme-music'
            shutil.move(loose_theme_file, os.path.join(theme_music_folder, 'theme.mp3'))
            print("[SYSTEM] Migrated existing 'theme.mp3' to 'theme-music' folder to support multiple themes.")
            
            # Configura a nova música para ir para a pasta criada
            final_folder = theme_music_folder
            final_file = os.path.join(final_folder, custom_name)
            
        # CASO 3: É a primeira vez (sem pasta e sem ficheiro solto) e só há uma música na fila
        else:
            final_folder = anime_folder
            final_file = os.path.join(final_folder, 'theme.mp3')
    else:
        raise ValueError("Theme type must be 'main' or 'season'.")

    # Garante que a pasta final (qualquer que seja a decisão acima) seja criada
    os.makedirs(final_folder, exist_ok=True)
    return final_file

def normalize_and_save(input_file, full_output_path, target_lufs):
    print(f"\n[AUDIO] Normalizing (Target: {target_lufs} LUFS) -> {full_output_path}")
    command = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
        '-i', input_file, '-filter:a', f'loudnorm=I={target_lufs}:LRA=11:TP=-1.0', '-b:a', '320k',
        full_output_path
    ]
    
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    subprocess.run(command, check=True, startupinfo=startupinfo)
    print("[AUDIO] Success! File is ready.")

def move_loose_episodes(root_folder, season_folder):
    media_extensions = ('.mkv', '.mp4', '.avi', '.ass', '.srt', '.vtt')
    temp_path = os.path.join(root_folder, season_folder)
    os.makedirs(temp_path, exist_ok=True)
    
    moved_files = 0
    for item in os.listdir(root_folder):
        item_path = os.path.join(root_folder, item)
        if os.path.isfile(item_path) and item.lower().endswith(media_extensions):
            new_path = os.path.join(temp_path, item)
            shutil.move(item_path, new_path)
            moved_files += 1
            
    if moved_files > 0:
        print(f"\n[CLEANUP] Smart Organize: {moved_files} media file(s) moved!")

# =======================================================
# JELLYFIN & METADATA
# =======================================================
def clean_search_name(folder_name, remove_year=False):
    clean_name = folder_name.replace('：', ' ').replace('-', ' ')
    
    if remove_year:
        clean_name = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', clean_name)
    else:
        clean_name = re.sub(r'\[.*?\]|\{.*?\}', '', clean_name)
    
    clean_name = re.sub(r'\s+', ' ', clean_name)
    return clean_name.strip()

def fetch_jellyfin_data(folder_name, jellyfin_url, api_key):
    clean_url = jellyfin_url.rstrip('/')
    headers = {"X-Emby-Token": api_key} 

    def try_search(term):
        params = {
            "searchTerm": term,
            "IncludeItemTypes": "Series",
            "Recursive": "true",
            "Fields": "Genres"
        }
        try:
            res = requests.get(f"{clean_url}/Items", headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("Items") and len(data["Items"]) > 0:
                    series = data["Items"][0]
                    
                    genres_list = series.get("Genres", [])
                    genres_string = ", ".join(genres_list) if genres_list else ""

                    return {
                        "success": True, 
                        "official_name": series.get("Name"), 
                        "series_id": series.get("Id"),
                        "image_url": f"{clean_url}/Items/{series.get('Id')}/Images/Primary",
                        "genres": genres_string 
                    }
        except Exception:
            pass
        return {"success": False}

    # STEP 1: Precise Search
    precise_term = clean_search_name(folder_name, remove_year=False)
    print(f"\n[JELLYFIN] Searching (Precise Mode): '{precise_term}'...")
    result = try_search(precise_term)
    if result["success"]:
        print(f"[JELLYFIN] ✅ Found: {result['official_name']}")
        return result

    # STEP 2: Generic Search
    generic_term = clean_search_name(folder_name, remove_year=True)
    if generic_term != precise_term:
        print(f"[JELLYFIN] ⚠️ Not found. Trying Generic Search: '{generic_term}'...")
        result = try_search(generic_term)
        if result["success"]:
            print(f"[JELLYFIN] ✅ Found via Fallback: {result['official_name']}")
            return result

    # STEP 3: Broad Search
    words = generic_term.split()
    if len(words) > 1:
        broad_term = " ".join(words[:2])
        print(f"[JELLYFIN] ⚠️ Not found. Trying Broad Search: '{broad_term}'...")
        result = try_search(broad_term)
        if result["success"]:
            print(f"[JELLYFIN] ✅ Found via Broad Search: {result['official_name']}")
            return result

    # STEP 4: Ultra Broad Search
    if len(words) > 0:
        ultra_broad_term = words[0]
        print(f"[JELLYFIN] ⚠️ Not found. Trying Ultra Broad Search: '{ultra_broad_term}'...")
        result = try_search(ultra_broad_term)
        if result["success"]:
            print(f"[JELLYFIN] ✅ Found via Ultra Broad Search: {result['official_name']}")
            return result

    print(f"[JELLYFIN] ❌ No series found for folder '{folder_name}'.")
    return {"success": False}

def download_jellyfin_image(image_url, api_key, dest_folder, file_name="cover.jpg"):
    headers = {"X-Emby-Token": api_key}
    full_path = os.path.join(dest_folder, file_name)
    
    try:
        print(f"[JELLYFIN] 📥 Starting cover image download...")
        res = requests.get(image_url, headers=headers, stream=True, timeout=15)
        
        if res.status_code == 200:
            os.makedirs(dest_folder, exist_ok=True)
            with open(full_path, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[JELLYFIN] 💾 Image saved successfully at: {full_path}")
            return full_path
        else:
            print(f"[JELLYFIN] ❌ Failed to download image. Server returned Status: {res.status_code}")
            return None
    except Exception as e:
        print(f"[JELLYFIN] ❌ Error during image download: {e}")
        return None

def fetch_jellyfin_season_image(series_id, season_num, jellyfin_url, api_key):
    clean_url = jellyfin_url.rstrip('/')
    headers = {"X-Emby-Token": api_key}
    try:
        res = requests.get(f"{clean_url}/Shows/{series_id}/Seasons", headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for season in data.get("Items", []):
                if season.get("IndexNumber") == season_num:
                    season_id = season.get("Id")
                    if season_id:
                        print(f"[JELLYFIN] 🖼️ Found Season {season_num} specific cover!")
                        return f"{clean_url}/Items/{season_id}/Images/Primary"
    except Exception as e:
        print(f"[JELLYFIN] ❌ Error fetching season {season_num} data: {e}")
    return None

def inject_mp3_metadata(mp3_path, image_path, title, album, genre):
    try:
        audio = MP3(mp3_path, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass 
            
        audio.tags.add(TIT2(encoding=3, text=title)) 
        audio.tags.add(TALB(encoding=3, text=album)) 
        
        if genre:
            audio.tags.add(TCON(encoding=3, text=genre)) 
        
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                image_data = f.read()
                
            mime_type = 'image/png' if image_path.lower().endswith('.png') else 'image/jpeg'
            
            audio.tags.add(
                APIC(
                    encoding=3,       
                    mime=mime_type,   
                    type=3,           
                    desc=u'Cover',    
                    data=image_data 
                )
            )
        
        audio.save(v2_version=3)
        return True
    except Exception as e:
        print(f"[MP3] ❌ Error injecting metadata: {e}")
        return False

def process_folder_artwork(anime_folder_path, anime_folder_name, config):
    print(f"\n[AUTOMATION] 🎬 Starting metadata processing for: {anime_folder_name}")
    
    local_cover_names = ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "poster.jpg", "poster.png"]
    final_image_path = None
    temp_image = False 
    
    final_genre = "" 
    final_album_name = anime_folder_name 
    series_id = None

    for file_name in local_cover_names:
        test_path = os.path.join(anime_folder_path, file_name)
        if os.path.exists(test_path):
            print(f"[AUTOMATION] 🔍 Priority 2 Triggered: Local image found ({file_name})")
            final_image_path = test_path
            break

    jelly_url = config.get("jelly_url")
    jelly_api = config.get("jelly_api")
    
    if jelly_url and jelly_api:
        print("[AUTOMATION] 🌐 Querying Jellyfin for additional metadata...")
        search_result = fetch_jellyfin_data(anime_folder_name, jelly_url, jelly_api)
        
        if search_result["success"]:
            final_genre = search_result["genres"]
            final_album_name = search_result["official_name"]
            series_id = search_result["series_id"]
            
            if final_genre:
                print(f"[AUTOMATION] 🏷️ Genres found: {final_genre}")
            
            if not final_image_path and search_result["image_url"]:
                temp_folder = tempfile.gettempdir()
                temp_file_name = f"temp_cover_{series_id}.jpg"
                
                final_image_path = download_jellyfin_image(
                    image_url=search_result["image_url"],
                    api_key=jelly_api,
                    dest_folder=temp_folder,
                    file_name=temp_file_name
                )
                temp_image = True
    else:
        print("[AUTOMATION] ⚠️ Jellyfin not configured/disabled. Skipping online search.")

    print("[AUTOMATION] 🚀 Scanning folder to apply metadata to MP3 files...")
    mp3_found = 0
    
    season_images_cache = {} 
    
    for root, subfolders, files in os.walk(anime_folder_path):
        for file in files:
            if file.lower().endswith('.mp3'):
                full_mp3_path = os.path.join(root, file)
                music_title = os.path.splitext(file)[0]
                
                current_image_path = final_image_path
                
                season_match = re.search(r'Season\s+(\d+)', root, re.IGNORECASE)
                
                if season_match and series_id and jelly_url and jelly_api:
                    season_num = int(season_match.group(1))
                    
                    if season_num in season_images_cache:
                        current_image_path = season_images_cache[season_num] or final_image_path
                    else:
                        print(f"[AUTOMATION] 🔍 Looking for Season {season_num} specific cover on Jellyfin...")
                        season_image_url = fetch_jellyfin_season_image(series_id, season_num, jelly_url, jelly_api)
                        
                        if season_image_url:
                            temp_folder = tempfile.gettempdir()
                            temp_file_name = f"temp_cover_{series_id}_S{season_num}.jpg"
                            
                            downloaded_season_path = download_jellyfin_image(
                                image_url=season_image_url,
                                api_key=jelly_api,
                                dest_folder=temp_folder,
                                file_name=temp_file_name
                            )
                            if downloaded_season_path:
                                season_images_cache[season_num] = downloaded_season_path
                                current_image_path = downloaded_season_path
                            else:
                                season_images_cache[season_num] = None
                        else:
                            print(f"[JELLYFIN] ⚠️ Cover for Season {season_num} not found. Using main cover fallback.")
                            season_images_cache[season_num] = None

                if inject_mp3_metadata(full_mp3_path, current_image_path, music_title, final_album_name, final_genre):
                    mp3_found += 1
                    
    print(f"[AUTOMATION] ✨ Done! Metadata applied to {mp3_found} MP3 file(s).")
    
    if temp_image and final_image_path:
        try:
            os.remove(final_image_path)
        except Exception:
            pass
            
    for s_img in season_images_cache.values():
        if s_img and os.path.exists(s_img):
            try:
                os.remove(s_img)
            except Exception:
                pass

# =======================================================
# JS -> PYTHON COMMUNICATION BRIDGE (API CLASS)
# =======================================================
class Api:
    def select_folder(self):
        try:
            folder = ""
            if len(webview.windows) > 0:
                result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                if result:
                    folder = result[0]
            else:
                root = tk.Tk()
                root.withdraw() 
                root.attributes('-topmost', True) 
                folder = filedialog.askdirectory(title="Select Media Directory")
                root.destroy()
            
            if not folder:
                return {"success": False, "error": "No folder selected."}
                
            seasons = []
            try:
                for item in os.listdir(folder):
                    if os.path.isdir(os.path.join(folder, item)) and item != "theme-music":
                        seasons.append(item)
            except Exception as e:
                print(f"Error reading folder: {e}")
                
            return {"success": True, "path": folder, "seasons": seasons}
            
        except Exception as e:
            print(f"Fatal error in Browse: {e}")
            return {"success": False, "error": str(e)}
        
    def _resolve_smart_folders(self, folder, batch_mode):
        if not folder: 
            return folder
        
        current_folder = os.path.normpath(folder)
        
        for _ in range(3):
            name = os.path.basename(current_folder).lower()
            if "season" in name or "theme" in name or "main" in name:
                current_folder = os.path.dirname(current_folder)
            else:
                break
                
        anime_folder = current_folder
        
        if not batch_mode:
            return anime_folder
        else:
            is_anime = False
            try:
                for item in os.listdir(anime_folder):
                    item_lower = item.lower()
                    if item_lower == "theme-music" or item_lower.startswith("season"):
                        is_anime = True
                        break
                    if os.path.isfile(os.path.join(anime_folder, item)) and item_lower.endswith(('.mkv', '.mp4', '.avi', '.mp3')):
                        is_anime = True
                        break
            except:
                pass
                
            if is_anime:
                parent_folder = os.path.dirname(anime_folder)
                if os.path.ismount(parent_folder) or len(parent_folder) <= 3:
                    return anime_folder
                return parent_folder
            else:
                return anime_folder

    def _auto_organize_single_season(self, anime_folder):
        try:
            items_in_folder = os.listdir(anime_folder)
            has_season = any("season" in item.lower() for item in items_in_folder if os.path.isdir(os.path.join(anime_folder, item)))
            
            if not has_season:
                anime_name = os.path.basename(anime_folder)
                new_season_name = f"Season 01. {anime_name}"
                new_season_path = os.path.join(anime_folder, new_season_name)
                
                media_extensions = ('.mkv', '.mp4', '.avi', '.ass', '.srt', '.vtt')
                moved_items = 0
                
                for item in items_in_folder:
                    item_path = os.path.join(anime_folder, item)
                    
                    if os.path.isfile(item_path) and item.lower().endswith(media_extensions):
                        os.makedirs(new_season_path, exist_ok=True)
                        shutil.move(item_path, os.path.join(new_season_path, item))
                        moved_items += 1
                        
                    elif os.path.isdir(item_path) and item.lower() == "theme-music":
                        os.makedirs(new_season_path, exist_ok=True)
                        shutil.move(item_path, os.path.join(new_season_path, item))
                        moved_items += 1
                        
                if moved_items > 0:
                    print(f"\n[AUTO-ORGANIZE] 🧹 {moved_items} item(s) automatically organized into '{new_season_name}'!")
        except Exception as e:
            print(f"[AUTO-ORGANIZE] ❌ Error organizing folder {anime_folder}: {e}")

    def enhance_local_music(self, target_folder, batch_mode, target_lufs, options=None):
        if options is None:
            options = {"normalize": True, "metadata": True, "organize": True}
            
        if not target_folder or not os.path.exists(target_folder):
            return {"status": "error", "message": "Invalid directory."}
        
        if batch_mode:
            target_folder = self._resolve_smart_folders(target_folder, batch_mode)
            
        try:
            print("\n=======================================================")
            print("[ENHANCE] Starting audio enhancement process...")
            print(f"[ENHANCE] Batch Mode (All subfolders): {'Yes' if batch_mode else 'No'}")
            print(f"[ENHANCE] Target Volume: {target_lufs} LUFS")
            print(f"[ENHANCE] Active Options: {options}")
            print("=======================================================\n")

            affected_files = 0
            folders_to_process = []
            
            if batch_mode:
                for item in os.listdir(target_folder):
                    item_path = os.path.join(target_folder, item)
                    if os.path.isdir(item_path):
                        folders_to_process.append(item_path)
            else:
                folders_to_process.append(target_folder)

            current_config = self.get_settings() 
            
            for anime_folder in folders_to_process:
                anime_name = os.path.basename(anime_folder)
                
                if options.get("organize", True):
                    self._auto_organize_single_season(anime_folder)
                
                if not options.get("normalize", True) and not options.get("metadata", True):
                    continue

                mp3s_in_folder = []
                
                for root, _, files in os.walk(anime_folder):
                    for file in files:
                        if file.lower().endswith('.mp3'):
                            mp3_path = os.path.join(root, file)
                            mp3s_in_folder.append(mp3_path)
                
                if not mp3s_in_folder:
                    continue 
                
                print(f"\n[ENHANCE] ✨ Enhancing audio in folder: {anime_name}")
                
                for mp3 in mp3s_in_folder:
                    if options.get("normalize", True):
                        print(f"[ENHANCE] 🎚️ Normalizing: {os.path.basename(mp3)}")
                        if normalize_audio_ffmpeg(mp3, target_lufs):
                            affected_files += 1
                    else:
                        affected_files += 1 
                            
                if options.get("metadata", True):
                    process_folder_artwork(anime_folder, anime_name, current_config)
                
            print("\n=======================================================")
            print(f"[ENHANCE] Complete! {affected_files} file(s) modified/read.")
            print("=======================================================\n")
            
            if affected_files > 0 or options.get("organize", True):
                return {"status": "success", "message": "Done! Process completed successfully."}
            else:
                return {"status": "success", "message": "No .mp3 files found to enhance."}
                
        except Exception as e:
            print(f"\n[ENHANCE] ❌ Critical error: {e}")
            return {"status": "error", "message": f"Error: {str(e)}"}
        
    def delete_music_folder(self, root_folder, batch_mode=False):
            if not root_folder or not os.path.exists(root_folder):
                return {"status": "error", "message": "Invalid or missing directory."}
        
            # Apply Mother/Grandmother intelligence
            target_folder = self._resolve_smart_folders(root_folder, batch_mode)
        
            deleted_count = 0
            try:
                print(f"\n=======================================================")
                print(f"[CLEANUP] Starting audio cleanup in: {target_folder}")
                print(f"[CLEANUP] Mode: {'ALL ANIMES (Grandmother)' if batch_mode else 'CURRENT ANIME (Mother)'}")
                print(f"=======================================================\n")
            
                # Scan everything starting from the target folder
                for root, subfolders, files in os.walk(target_folder):
                    for file in files:
                        if file.lower().endswith('.mp3'):
                            full_path = os.path.join(root, file)
                            os.remove(full_path)
                            print(f"[CLEANUP] 🗑️ Removed: {file}")
                            deleted_count += 1
            
                # Clean up empty "theme-music" folders
                for root, subfolders, files in os.walk(target_folder, topdown=False):
                    for subfolder in subfolders:
                        if subfolder.lower() == 'theme-music':
                            sub_path = os.path.join(root, subfolder)
                            if not os.listdir(sub_path): 
                                os.rmdir(sub_path)
                            
                print(f"\n[CLEANUP] Done! {deleted_count} file(s) removed.")
                return {"status": "success", "message": f"Cleaned up! {deleted_count} audio file(s) removed."}
            
            except Exception as e:
                print(f"[CLEANUP] ❌ Error: {e}")
                return {"status": "error", "message": f"Error during cleanup: {str(e)}"}

    def get_status(self):
        global global_state
        logs = ""
        while not log_queue.empty():
            logs += log_queue.get()
                
        return {
            "logs": logs,
            "is_processing": global_state["is_processing"],
            "percentage": global_state["percentage"],
            "statusText": global_state["statusText"],
            "percentageText": global_state["percentageText"],
            "item_statuses": global_state["item_statuses"]
        }
    
    def retry_single_item(self, index, music, root_anime_folder):
        global global_state
        global_state["is_processing"] = True
        global_state["item_statuses"][index] = "processing"
        global_state["statusText"] = f"Retrying: {music.get('name', music.get('nome'))}..."
        
        t = threading.Thread(target=self._execute_single_retry_thread, args=(index, music, root_anime_folder))
        t.daemon = True
        t.start()
        return True

    def _execute_single_retry_thread(self, index, music, root_anime_folder):
        global global_state
        
        link = music['link']
        name = music.get('name', music.get('nome'))
        destination = music.get('destination', music.get('destino'))
        lufs = music['lufs']
        has_multi_main = music.get('has_multi_main', False)
        
        print(f"\n[SYSTEM] Retrying single item: {name}...\n")
        
        downloaded_file = None
        try:
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    downloaded_file = download_music(link)
                    break
                except Exception as dl_error:
                    if attempt == max_attempts - 1:
                        raise dl_error
                    print(f"[RETRY] ⚠️ Attempt {attempt + 1} failed for '{name}'. Retrying...")
                    
            global_state["statusText"] = f"Normalizing: {name}..."
            
            if "Season" in destination:
                theme_type = "season"
                temp_folder = destination
            else:
                theme_type = "main"
                temp_folder = None

            final_path = generate_destination_path(root_anime_folder, theme_type, name, temp_folder, multiple_main=has_multi_main)
            normalize_and_save(downloaded_file, final_path, lufs)
            
            if "Season" in destination:
                move_loose_episodes(root_anime_folder, destination)
                
            current_config = load_config()
            anime_name = os.path.basename(root_anime_folder)
            if not current_config.get("jelly_check"):
                current_config["jelly_url"] = ""
                current_config["jelly_api"] = ""
            process_folder_artwork(root_anime_folder, anime_name, current_config)
            
            global_state["item_statuses"][index] = "completed"
            global_state["statusText"] = "Item processed successfully!"
            print(f"[SUCCESS] Single retry for {name} completed!")
            
        except Exception as e:
            print(f"\n[ERROR] Single retry failed for {name}: {str(e)}\n")
            global_state["item_statuses"][index] = "error"
            global_state["statusText"] = f"Failed to retry {name}"
            
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                except Exception as e:
                    print(f"[WARNING] Could not delete temporary file: {e}")
            
            if "processing" not in global_state["item_statuses"]:
                global_state["is_processing"] = False

    def process_queue(self, music_list, root_anime_folder):
        global global_state
        global_state["is_processing"] = True
        global_state["percentage"] = 0
        global_state["statusText"] = "Starting..."
        global_state["percentageText"] = "0%"
        global_state["item_statuses"] = ["waiting"] * len(music_list)

        t = threading.Thread(target=self._execute_queue_thread, args=(music_list, root_anime_folder))
        t.daemon = True
        t.start()
        return True

    def _execute_queue_thread(self, music_list, root_anime_folder):
        global global_state

        total = len(music_list)

        global_state["item_statuses"] = ["waiting"] * total 
        global_state["percentage"] = 0
        global_state["is_processing"] = True
        global_state["statusText"] = "Starting process..."
        global_state["percentageText"] = f"0/{total} (0%)"

        print(f"\n[SYSTEM] Starting queue with {total} items...\n")

        main_count = sum(1 for m in music_list if m.get('destination', m.get('destino')) == 'Main Theme')
        has_multi_main = main_count > 1
        seasons_to_clean = set()

        for i, music in enumerate(music_list):
            link = music['link']
            name = music.get('name', music.get('nome'))
            destination = music.get('destination', music.get('destino'))
            lufs = music['lufs']
            
            percentage = int((i / total) * 100)
            perc_text = f"{percentage}%" if i == 0 else f"{i}/{total} ({percentage}%)"

            global_state["item_statuses"][i] = "processing"
            global_state["percentage"] = percentage
            global_state["statusText"] = f"Downloading: {name}..."
            global_state["percentageText"] = perc_text

            downloaded_file = None 
            try:
                max_attempts = 2
                for attempt in range(max_attempts):
                    try:
                        downloaded_file = download_music(link)
                        break
                    except Exception as dl_error:
                        if attempt == max_attempts - 1:
                            raise dl_error
                        print(f"[RETRY] ⚠️ Attempt {attempt + 1} failed to download '{name}'. Retrying automatically...")
                
                global_state["statusText"] = f"Normalizing: {name}..."
                
                if "Season" in destination:
                    theme_type = "season"
                    temp_folder = destination
                    seasons_to_clean.add(temp_folder)
                else:
                    theme_type = "main"
                    temp_folder = None

                final_path = generate_destination_path(root_anime_folder, theme_type, name, temp_folder, multiple_main=has_multi_main)
                normalize_and_save(downloaded_file, final_path, lufs)
                
                global_state["item_statuses"][i] = "completed"
                print(f"[SUCCESS] {name} finished successfully!")
                
            except Exception as e:
                print(f"\n[ERROR] Failed to process {name}: {str(e)}\n")
                global_state["item_statuses"][i] = "error"
                
            finally:
                # GUARANTEED CLEANUP
                if downloaded_file and os.path.exists(downloaded_file):
                    try:
                        os.remove(downloaded_file)
                    except Exception as e:
                        print(f"[WARNING] Could not delete temporary file: {e}")

        if seasons_to_clean:
            print("\n[SYSTEM] Starting Smart Cleanup on affected seasons...")
            for temp in seasons_to_clean:
                move_loose_episodes(root_anime_folder, temp)

        global_state["percentage"] = 99
        global_state["statusText"] = "Applying Cover Arts..."
        global_state["percentageText"] = "99%"
        
        current_config = load_config()
        anime_name = os.path.basename(root_anime_folder)
        
        if not current_config.get("jelly_check"):
            current_config["jelly_url"] = ""
            current_config["jelly_api"] = ""

        process_folder_artwork(root_anime_folder, anime_name, current_config)

        # Process complete!
        global_state["percentage"] = 100
        global_state["statusText"] = "All operations completed!"
        global_state["percentageText"] = f"{total}/{total} (100%)"
        global_state["is_processing"] = False 
        
        print("\n[SYSTEM] Queue completed successfully! Waiting for new commands...")


    def test_jellyfin(self, url, api_key):
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
            url = str(url).strip().strip('"').strip("'")
            api_key = str(api_key).strip().strip('"').strip("'")
                
            if not url.startswith('http'):
                url = 'http://' + url
            clean_url = url.rstrip('/')
                
            headers = {
                "X-Emby-Token": api_key,
                "Accept": "application/json"
            }
                
            response = requests.get(f"{clean_url}/System/Info", headers=headers, timeout=5, verify=False)
                
            if response.status_code == 200:
                return {"status": "success", "message": "✅ Connected Successfully!"}
            else:
                return {"status": "error", "message": f"❌ Error {response.status_code}: API Key rejected by server."}
                    
        except Exception as e:
            return {"status": "error", "message": f"❌ Connection Error: {str(e)}"}
            
    def get_settings(self):
        return load_config()

    def save_settings(self, data):
        save_config(data)
        return True

# ========================================================
# GLOBAL SYSTEM STATE (Polling Pattern)
# ========================================================
global_state = {
    "is_processing": False,
    "percentage": 0,
    "statusText": "Ready",
    "percentageText": "0%",
    "item_statuses": [] 
}

# ========================================================
# FLASK ROUTES (BROWSER MODE API)
# ========================================================
api_system = Api() 

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/select_folder', methods=['POST'])
def api_flask_select_folder():
    result = api_system.select_folder()
    return jsonify(result)

@app.route('/api/get_settings', methods=['GET'])
def api_flask_get_settings():
    return jsonify(api_system.get_settings())

@app.route('/api/save_settings', methods=['POST'])
def api_flask_save_settings():
    data = request.json
    api_system.save_settings(data)
    return jsonify({"status": "success"})

@app.route('/api/process_queue', methods=['POST'])
def api_flask_process_queue():
    data = request.json
    queue_data = data.get('queue', data.get('fila', []))
    folder = data.get('folder', data.get('pasta', ''))
    api_system.process_queue(queue_data, folder)
    return jsonify({"status": "success"})

@app.route('/api/status', methods=['GET'])
def api_flask_status():
    return jsonify(api_system.get_status())

@app.route('/api/test_jellyfin', methods=['POST'])
def api_flask_test_jellyfin():
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        url = data.get('url', '')
        api_key = data.get('api_key', data.get('api', '')) 
        
        print(f"\n[RECEIVED FROM BROWSER] URL: {url} | API: {api_key}")
        
        result = api_system.test_jellyfin(url, api_key)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"❌ Flask Route Error: {str(e)}"})
    
@app.route('/api/delete_music_folder', methods=['POST'])
def api_flask_delete_music():
    try:
        data = request.get_json(force=True, silent=True) or {}
        folder = data.get('folder', data.get('pasta', ''))
        batch_mode = data.get('batchMode', data.get('modoBatch', False))
        
        print(f"\n[RECEIVED FROM BROWSER] Delete files in: {folder} | Batch: {batch_mode}")
        
        result = api_system.delete_music_folder(folder, batch_mode)
        return jsonify(result)
        
    except Exception as e:
        print(f"[FLASK ERROR] Delete failed: {e}")
        return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"})

@app.route('/api/enhance_local_music', methods=['POST'])
def api_flask_enhance_music():
    try:
        data = request.get_json(force=True, silent=True) or {}
        
        folder = data.get('folder', data.get('pasta', ''))
        batch_mode = data.get('batchMode', data.get('modoBatch', False))
        lufs = data.get('lufs', '-24')
        options = data.get('options', data.get('opcoes', None))
        
        print(f"\n[RECEIVED FROM BROWSER] Enhance - Folder: {folder} | Batch: {batch_mode} | LUFS: {lufs} | Options: {options}")
        
        result = api_system.enhance_local_music(folder, batch_mode, lufs, options)
        return jsonify(result)
        
    except Exception as e:
        print(f"[FLASK ERROR] Enhance failed: {e}")
        return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"})
    
@app.route('/api/retry_item', methods=['POST'])
def api_flask_retry_item():
    try:
        data = request.get_json(force=True, silent=True) or {}
        index = data.get('index')
        music = data.get('music')
        folder = data.get('folder', '')
        
        api_system.retry_single_item(index, music, folder)
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"[FLASK ERROR] Retry item failed: {e}")
        return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"})

# ========================================================
# STARTUP & MAIN EXECUTION
# ========================================================
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