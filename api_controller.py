import os
import threading
import re
import tempfile
import webview
import shutil
import requests
import subprocess
import zipfile
from datetime import datetime
from mutagen.mp3 import MP3

from core.config import load_config, save_config, APP_ROOT_DIR
from core.logger import log_queue
from core.audio import download_music, normalize_and_save, normalize_audio_ffmpeg, inject_mp3_metadata, get_streaming_url
from core.jellyfin import fetch_jellyfin_data, download_jellyfin_image, fetch_jellyfin_season_image, find_jellyfin_item
from core.files import generate_destination_path, move_loose_episodes, clean_search_name

global_state = {
    "is_processing": False,
    "percentage": 0,
    "statusText": "Ready",
    "percentageText": "0%",
    "item_statuses": [] 
}

def process_folder_artwork(anime_folder_path, anime_folder_name, config, only_file=None):
    print(f"\n[AUTOMATION] 🎬 Starting metadata processing for: {anime_folder_name}")
    
    local_cover_names = ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "poster.jpg", "poster.png"]
    final_image_path = None
    temp_image = False 
    
    final_genre = "" 
    final_album_name = anime_folder_name 
    series_id = None

    for file_name in local_cover_names:
        test_path = os.path.join(anime_folder_path, file_name)
        if os.path.exists(test_path) and os.path.getsize(test_path) > 1024:
            print(f"[AUTOMATION] 🔍 Priority 2 Triggered: Local image found ({file_name})")
            final_image_path = test_path
            break

    jelly_url = config.get("jelly_url")
    jelly_api = config.get("jelly_api")
    
    if jelly_url and jelly_api:
        print("[AUTOMATION] 🌐 Querying Jellyfin for additional metadata...")
        search_result = fetch_jellyfin_data(anime_folder_name, jelly_url, jelly_api, folder_path=anime_folder_path)
        
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
    
    if only_file:
        mp3_paths = [only_file]
    else:
        mp3_paths = [
            os.path.join(root, file)
            for root, _, files in os.walk(anime_folder_path)
            for file in files if file.lower().endswith('.mp3')
        ]

    for full_mp3_path in mp3_paths:
        root = os.path.dirname(full_mp3_path)
        music_title = os.path.splitext(os.path.basename(full_mp3_path))[0]

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
                    downloaded_season_path = download_jellyfin_image(
                        image_url=season_image_url,
                        api_key=jelly_api,
                        dest_folder=tempfile.gettempdir(),
                        file_name=f"temp_cover_{series_id}_S{season_num}.jpg"
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

def _start_background(target, *args):
    t = threading.Thread(target=target, args=args)
    t.daemon = True
    t.start()

def _download_with_retry(link, log_prefix, name):
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            return download_music(link)
        except Exception:
            if attempt == max_attempts - 1:
                raise
            print(f"{log_prefix} ⚠️ Attempt {attempt + 1} failed to download '{name}'. Retrying...")

def _artwork_config():
    """Config for process_folder_artwork: Jellyfin credentials blanked when the integration is disabled"""
    config = load_config()
    if not config.get("jelly_check"):
        config["jelly_url"] = ""
        config["jelly_api"] = ""
    return config

def _is_single_media_folder(base_path):
    """True when base_path is one media folder (has theme files or season folders) instead of the library root"""
    if os.path.exists(os.path.join(base_path, "theme.mp3")):
        return True
    if os.path.isdir(os.path.join(base_path, "theme-music")):
        return True
    for item in os.listdir(base_path):
        if os.path.isdir(os.path.join(base_path, item)) and (item.lower().startswith("season") or item.lower() == "specials"):
            return True
    return False

def _is_season_folder_name(name):
    name = name.lower()
    return "season" in name or "temporada" in name or name == "specials"

def _media_folder_of_track(file_path):
    """Media folder that owns a theme track: <media>/theme.mp3, <media>/theme-music/x.mp3 or <media>/<season>/theme-music/x.mp3"""
    parent = os.path.dirname(file_path)
    if os.path.basename(parent).lower() != "theme-music":
        return parent if os.path.basename(file_path).lower() == "theme.mp3" else None

    owner = os.path.dirname(parent)
    if _is_season_folder_name(os.path.basename(owner)):
        return os.path.dirname(owner)
    return owner

def _library_root(base_path):
    return os.path.dirname(base_path) if _is_single_media_folder(base_path) else base_path

def _track_entry(file_path, file_name, location_type, error_label):
    duration = 0.0
    try:
        duration = MP3(file_path).info.length
    except Exception as e:
        print(f"[LIBRARY] Error reading {error_label}: {e}")

    return {
        "file_name": file_name,
        "file_path": file_path,
        "location_type": location_type,
        "duration": duration,
        "startTime": "0",
        "endTime": f"{int(duration)}" if duration > 0 else "0"
    }

def _theme_folder_tracks(theme_folder, location_type, error_label):
    tracks = []
    if os.path.isdir(theme_folder):
        for file in os.listdir(theme_folder):
            if file.lower().endswith('.mp3'):
                tracks.append(_track_entry(os.path.join(theme_folder, file), file, location_type, f"{error_label} {file}"))
    return tracks

def _list_season_folders(folder):
    seasons = []
    for item in os.listdir(folder):
        if os.path.isdir(os.path.join(folder, item)):
            item_lower = item.lower()
            if "season" in item_lower or "temporada" in item_lower or "specials" in item_lower:
                seasons.append(item)
    return sorted(seasons)

def _powershell_dialog(script):
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return res.stdout.strip()

class Api:
    def select_folder(self):
        folder = ""
        seasons = []
        try:
            if len(webview.windows) > 0:
                active_window = next(iter(webview.windows))
                result = active_window.create_file_dialog(webview.FOLDER_DIALOG)
                if result:
                    folder = next(iter(result))
            else:
                cmd = (
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null;"
                    "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog;"
                    "$dialog.Description = 'Select Media Directory';"
                    "$dialog.ShowNewFolderButton = $true;"
                    "if($dialog.ShowDialog() -eq 'OK') { $dialog.SelectedPath }"
                )
                folder = _powershell_dialog(cmd)

            if folder and os.path.exists(folder):
                seasons = _list_season_folders(folder)

        except Exception as e:
            print(f"[API] Error selecting folder: {e}")
            
        return {
            "success": bool(folder),
            "path": folder,
            "seasons": seasons
        }
        
    def resolve_jellyfin_item(self, item_id):
        """Media folder of a Jellyfin item, in the same shape as select_folder"""
        config = load_config()
        jelly_url, jelly_api = config.get("jelly_url"), config.get("jelly_api")
        if not (config.get("jelly_check") and jelly_url and jelly_api):
            return {"success": False, "message": "Jellyfin is not configured in Settings."}

        item = find_jellyfin_item(str(item_id).strip(), jelly_url, jelly_api)
        if not item or not item.get("Path"):
            return {"success": False, "message": "This item was not found on Jellyfin."}

        folder = os.path.dirname(item["Path"]) if item.get("Type") == "Movie" else item["Path"]
        if not os.path.isdir(folder):
            print(f"[JELLYFIN] ⚠️ '{item.get('Name')}' lives at '{folder}', which Themarr cannot see.")
            return {"success": False, "message": f"Folder not visible from Themarr: {folder}"}

        print(f"[JELLYFIN] 🔗 Opened from Jellyfin: {item.get('Name')} -> {folder}")
        return {"success": True, "path": folder, "seasons": _list_season_folders(folder), "name": item.get("Name")}

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
            
            season_folders = [item for item in items_in_folder if os.path.isdir(os.path.join(anime_folder, item)) and "season" in item.lower()]
            has_season = len(season_folders) > 0
            
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
                        
                if moved_items > 0:
                    print(f"\n[AUTO-ORGANIZE] 🧹 {moved_items} item(s) automatically organized into '{new_season_name}'!")
                    season_folders = [new_season_name] 
            
            items_in_folder = os.listdir(anime_folder)
            
            has_root_music = False
            for item in items_in_folder:
                item_lower = item.lower()
                if item_lower == "theme-music" and os.path.isdir(os.path.join(anime_folder, item)):
                    has_root_music = True
                elif item_lower == "theme.mp3" and os.path.isfile(os.path.join(anime_folder, item)):
                    has_root_music = True
                    
            if not has_root_music and len(season_folders) == 1:
                only_season_path = os.path.join(anime_folder, season_folders[0])
                season_items = os.listdir(only_season_path)
                
                for s_item in season_items:
                    if s_item.lower() == "theme-music" and os.path.isdir(os.path.join(only_season_path, s_item)):
                        shutil.move(os.path.join(only_season_path, s_item), os.path.join(anime_folder, s_item))
                        print(f"\n[AUTO-ORGANIZE] 🎵 Promoted 'theme-music' from '{season_folders[0]}' to Main Anime Folder!")
                        break
                        
        except Exception as e:
            print(f"[AUTO-ORGANIZE] ❌ Error organizing folder {anime_folder}: {e}")

    def enhance_local_music(self, target_folder, scope, target_lufs, options=None, selected_folders=None):
        if options is None:
            options = {"normalize": True, "metadata": True, "organize": True}
            
        if not target_folder or not os.path.exists(target_folder):
            return {"status": "error", "message": "Invalid directory."}
        
        is_batch = (scope == 'all' or scope == 'selected')
        
        if is_batch:
            target_folder = self._resolve_smart_folders(target_folder, is_batch)
            
        global_state["is_processing"] = True
        global_state["percentage"] = 0
        global_state["statusText"] = "Starting Enhancement..."
        global_state["percentageText"] = "0%"

        _start_background(self._execute_enhance_thread, target_folder, scope, target_lufs, options, selected_folders)
        
        return {"status": "success", "message": "Enhancement started in background!"}

    def _execute_enhance_thread(self, target_folder, scope, target_lufs, options, selected_folders):
        try:
            print("\n=======================================================")
            print("[ENHANCE] Starting audio enhancement process...")
            print(f"[ENHANCE] Scope Mode: {scope}")
            print(f"[ENHANCE] Target Volume: {target_lufs} LUFS")
            print("=======================================================\n")

            affected_files = 0
            folders_to_process = []
            
            if scope == 'all':
                for item in os.listdir(target_folder):
                    item_path = os.path.join(target_folder, item)
                    if os.path.isdir(item_path):
                        folders_to_process.append(item_path)

            elif scope == 'selected' and selected_folders:
                for folder_name in selected_folders:
                    item_path = os.path.join(target_folder, folder_name)
                    if os.path.isdir(item_path):
                        folders_to_process.append(item_path)
            else:
                folders_to_process.append(target_folder)

            current_config = self.get_settings() 
            audio_effects = current_config.get("audio_fx", {})
            total_folders = len(folders_to_process)
            
            for i, anime_folder in enumerate(folders_to_process):
                anime_name = os.path.basename(anime_folder)
                
                percentage = int((i / total_folders) * 100) if total_folders > 0 else 0
                global_state["percentage"] = percentage
                global_state["statusText"] = f"Enhancing: {anime_name}"
                global_state["percentageText"] = f"{i}/{total_folders} ({percentage}%)"
                
                if options.get("organize", True):
                    self._auto_organize_single_season(anime_folder)
                
                if not options.get("normalize", True) and not options.get("metadata", True) and not options.get("audio_fx", False):
                    continue

                mp3s_in_folder = [
                    os.path.join(root, file)
                    for root, _, files in os.walk(anime_folder)
                    for file in files if file.lower().endswith('.mp3')
                ]
                
                if not mp3s_in_folder:
                    continue 
                
                print(f"\n[ENHANCE] ✨ Enhancing audio in folder: {anime_name}")
                normalize_active = options.get("normalize", True)
                fx_active = options.get("audio_fx", False)
                
                for mp3 in mp3s_in_folder:
                    if normalize_active or fx_active:
                        print(f"[ENHANCE] 🎚️ Processing Audio: {os.path.basename(mp3)}")
                        effs = audio_effects if fx_active else {}
                        if normalize_audio_ffmpeg(mp3, target_lufs, effs, normalize_enabled=normalize_active):
                            affected_files += 1
                    else:
                        affected_files += 1 
                            
                if options.get("metadata", True):
                    process_folder_artwork(anime_folder, anime_name, _artwork_config())
                
            print("\n=======================================================")
            print(f"[ENHANCE] Complete! {affected_files} file(s) modified/read.")
            print("=======================================================\n")
            
            global_state["percentage"] = 100
            global_state["statusText"] = "Enhancement Complete!"
            global_state["percentageText"] = f"{total_folders}/{total_folders} (100%)"
                
        except Exception as e:
            print(f"\n[ENHANCE] ❌ Critical error: {e}")
            global_state["statusText"] = f"Error: {str(e)}"
        finally:
            global_state["is_processing"] = False
        
    def delete_music_folder(self, root_folder, scope, selected_folders=None):

        if not root_folder or not os.path.exists(root_folder):
            return {"status": "error", "message": "Invalid or missing directory."}
        
        folders_to_process = []
        mode_str = ""

        if scope == 'all':
            target = self._resolve_smart_folders(root_folder, True)
            folders_to_process.append(target)
            mode_str = "ALL ANIMES (Grandmother)"
            
        elif scope == 'selected' and selected_folders:
            smart_root = self._resolve_smart_folders(root_folder, True)
            for folder_name in selected_folders:
                full_path = os.path.join(smart_root, folder_name)
                if os.path.exists(full_path):
                    folders_to_process.append(full_path)
            mode_str = f"SELECTED ANIMES ({len(folders_to_process)} folders)"
            
        else:
            target = self._resolve_smart_folders(root_folder, False)
            folders_to_process.append(target)
            mode_str = "CURRENT ANIME (Mother)"
    
        deleted_count = 0
        try:
            print(f"\n=======================================================")
            print(f"[CLEANUP] Starting audio cleanup")
            print(f"[CLEANUP] Mode: {mode_str}")
            print(f"=======================================================\n")
            
            for target_folder in folders_to_process:
                print(f"[CLEANUP] Scanning folder: {target_folder}")
                
                for root, subfolders, files in os.walk(target_folder):
                    for file in files:
                        if file.lower().endswith('.mp3'):
                            full_path = os.path.join(root, file)
                            os.remove(full_path)
                            print(f"[CLEANUP] 🗑️ Removed: {file}")
                            deleted_count += 1
                
                for root, subfolders, files in os.walk(target_folder, topdown=False):
                    for subfolder in subfolders:
                        if subfolder.lower() == 'theme-music':
                            sub_path = os.path.join(root, subfolder)
                            if not os.listdir(sub_path): 
                                os.rmdir(sub_path)
                                print(f"[CLEANUP] 📂 Removed empty folder: theme-music")
                                
            print(f"\n[CLEANUP] Done! {deleted_count} file(s) removed.")
            return {"status": "success", "message": f"Cleaned up! {deleted_count} audio file(s) removed."}
        
        except Exception as e:
            print(f"[CLEANUP] ❌ Error: {e}")
            return {"status": "error", "message": f"Error during cleanup: {str(e)}"}

    def get_status(self):
        chunks = []
        while not log_queue.empty():
            chunks.append(log_queue.get())

        return {
            "logs": "".join(chunks),
            "is_processing": global_state["is_processing"],
            "percentage": global_state["percentage"],
            "statusText": global_state["statusText"],
            "percentageText": global_state["percentageText"],
            "item_statuses": global_state["item_statuses"]
        }
    
    def retry_single_item(self, index, music, root_anime_folder):
        global_state["is_processing"] = True
        global_state["item_statuses"][index] = "processing"
        global_state["statusText"] = f"Retrying: {music.get('name')}..."
        
        _start_background(self._execute_single_retry_thread, index, music, root_anime_folder)
        return True

    def _execute_single_retry_thread(self, index, music, root_anime_folder):
        current_config = self.get_settings()
        audio_effects = current_config.get("audio_fx", {})
        
        link = music['link']
        name = music.get('name')
        destination = music.get('destination')
        lufs = music['lufs']
        has_multi_main = music.get('has_multi_main', False)

        track_fx = music.get('audio_fx') or audio_effects
        
        print(f"\n[SYSTEM] Retrying single item: {name}...\n")
        
        downloaded_file = None
        try:
            downloaded_file = _download_with_retry(link, "[RETRY]", name)

            global_state["statusText"] = f"Normalizing: {name}..."
            
            if "Season" in destination:
                theme_type = "season"
                temp_folder = destination
            else:
                theme_type = "main"
                temp_folder = None

            final_path = generate_destination_path(root_anime_folder, theme_type, name, temp_folder, multiple_main=has_multi_main)
            
            start_time = music.get('startTime', None)
            end_time = music.get('endTime', None)
            
            normalize_and_save(
                downloaded_file, 
                final_path, 
                lufs, 
                track_fx, 
                start_time=start_time, 
                end_time=end_time
            )
            
            if "Season" in destination:
                move_loose_episodes(root_anime_folder, destination)
                
            process_folder_artwork(root_anime_folder, os.path.basename(root_anime_folder), _artwork_config())
            
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
        global_state["is_processing"] = True
        global_state["percentage"] = 0
        global_state["statusText"] = "Starting..."
        global_state["percentageText"] = "0%"
        global_state["item_statuses"] = ["waiting"] * len(music_list)

        _start_background(self._execute_queue_thread, music_list, root_anime_folder)
        return True

    def _execute_queue_thread(self, music_list, root_anime_folder):
        try:
            self._run_queue(music_list, root_anime_folder)
        except Exception as e:
            print(f"\n[ERROR] Queue stopped by an unexpected error: {e}\n")
            global_state["statusText"] = f"Error: {str(e)}"
        finally:
            global_state["is_processing"] = False

    def _run_queue(self, music_list, root_anime_folder):
        current_config = self.get_settings()
        audio_effects = current_config.get("audio_fx", {})

        total = len(music_list)

        global_state["item_statuses"] = ["waiting"] * total
        global_state["percentage"] = 0
        global_state["is_processing"] = True
        global_state["statusText"] = "Starting process..."
        global_state["percentageText"] = f"0/{total} (0%)"

        print(f"\n[SYSTEM] Starting queue with {total} items...\n")

        main_count = sum(1 for m in music_list if m.get('destination') == 'Main Theme')
        has_multi_main = main_count > 1
        seasons_to_clean = set()

        for i, music in enumerate(music_list):
            link = music['link']
            name = music.get('name')
            destination = music.get('destination')
            lufs = music['lufs']

            track_fx = music.get('audio_fx') or audio_effects

            percentage = int((i / total) * 100)
            perc_text = f"{percentage}%" if i == 0 else f"{i}/{total} ({percentage}%)"

            global_state["item_statuses"][i] = "processing"
            global_state["percentage"] = percentage
            global_state["statusText"] = f"Downloading: {name}..."
            global_state["percentageText"] = perc_text

            downloaded_file = None
            try:
                downloaded_file = _download_with_retry(link, "[RETRY]", name)

                global_state["statusText"] = f"Normalizing: {name}..."

                if "Season" in destination:
                    theme_type = "season"
                    temp_folder = destination
                    seasons_to_clean.add(temp_folder)
                else:
                    theme_type = "main"
                    temp_folder = None

                final_path = generate_destination_path(root_anime_folder, theme_type, name, temp_folder, multiple_main=has_multi_main)

                normalize_and_save(
                    downloaded_file,
                    final_path,
                    lufs,
                    track_fx,
                    start_time=music.get('startTime'),
                    end_time=music.get('endTime')
                )

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

        process_folder_artwork(root_anime_folder, os.path.basename(root_anime_folder), _artwork_config())

        # Process complete!
        global_state["percentage"] = 100
        global_state["statusText"] = "All operations completed!"
        global_state["percentageText"] = f"{total}/{total} (100%)"

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

    def get_subfolders(self, folder_path):
        try:
            if not folder_path or not os.path.exists(folder_path):
                return {"status": "error", "folders": [], "selected_anime": ""}
            
            root_folder = self._resolve_smart_folders(folder_path, True)
            
            subfolders = [f for f in os.listdir(root_folder) if os.path.isdir(os.path.join(root_folder, f))]
            
            selected_anime = ""
            if root_folder.lower() != folder_path.lower():
                selected_anime = os.path.basename(folder_path)
                
            return {
                "status": "success", 
                "folders": subfolders, 
                "selected_anime": selected_anime
            }
        except Exception as e:
            print(f"[ERROR] get_subfolders failed: {str(e)}")
            return {"status": "error", "folders": [], "selected_anime": ""}
        
    def search_youtube(self, query):
        if not query or not query.strip():
            return []
            
        from yt_dlp import YoutubeDL
        
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'force_generic_extractor': False,
            'skip_download': True,
        }
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                search_result = ydl.extract_info(f"ytsearch35:{query}", download=False)
                
                results = []
                if 'entries' in search_result:
                    for entry in search_result['entries']:
                        if not entry:
                            continue
                            
                        duration_secs = entry.get('duration')
                        duration_str = "0:00"
                        if duration_secs:
                            mins = int(duration_secs // 60)
                            secs = int(duration_secs % 60)
                            duration_str = f"{mins}:{secs:02d}"
                        
                        video_id = entry.get('id')
                        thumb_url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else ""
                        
                        results.append({
                            'title': entry.get('title', 'Unknown Title'),
                            'url': f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get('url'),
                            'channel': entry.get('uploader', 'Unknown Channel'),
                            'duration': duration_str,
                            'thumbnail': thumb_url
                        })
                    return results
        except Exception as e:
            print(f"[YOUTUBE SEARCH ERROR] Failed to fetch data: {e}")
            return []
            
        return []

    def get_stream_info(self, url):
        """Return the direct streaming URL for a given YouTube link."""
        if not url:
            return {"success": False, "error": "No URL provided"}
        return get_streaming_url(url)

    def list_local_library(self, base_path, scope="all", selected_folders=None):
        """
        Scan media folders and return a structured list of available anime and their associated theme music tracks.
        Detects intelligently if the inserted path is the media root or a specific anime folder.
        """
        if not base_path or not os.path.exists(base_path):
            return {"success": False, "message": "Media Directory not found or not selected."}
            
        if selected_folders is None:
            selected_folders = []
            
        try:
            is_single_anime = _is_single_media_folder(base_path)
        except Exception:
            is_single_anime = False

        if is_single_anime:
            real_root_path = os.path.dirname(base_path)
            if not selected_folders:
                selected_folders = [os.path.basename(base_path)]
        else:
            real_root_path = base_path
            
        library_data = []
        
        try:
            all_items = os.listdir(real_root_path)
            anime_folders = [d for d in all_items if os.path.isdir(os.path.join(real_root_path, d))]
            
            for folder in anime_folders:
                if scope == "selected" and folder not in selected_folders:
                    continue
                    
                anime_path = os.path.join(real_root_path, folder)
                tracks = []
                
                single_theme_path = os.path.join(anime_path, "theme.mp3")
                if os.path.exists(single_theme_path):
                    tracks.append(_track_entry(single_theme_path, "theme.mp3", "Main Theme (Single)", f"theme.mp3 in {folder}"))

                tracks += _theme_folder_tracks(os.path.join(anime_path, "theme-music"), "Main Theme (Folder)", "root theme-music")

                try:
                    for subitem in os.listdir(anime_path):
                        subitem_path = os.path.join(anime_path, subitem)
                        if os.path.isdir(subitem_path):
                            tracks += _theme_folder_tracks(os.path.join(subitem_path, "theme-music"), subitem, "season track")
                except Exception as e:
                    print(f"[LIBRARY] Error reading subdirectories of {folder}: {e}")

                library_data.append({
                    "anime_name": folder,
                    "folder_path": anime_path,
                    "tracks": tracks
                })
                
            library_data.sort(key=lambda x: x["anime_name"].lower())
            return {"success": True, "library": library_data}
            
        except Exception as e:
            print(f"[LIBRARY] Error listing library: {e}")
            return {"success": False, "message": str(e)}

    def process_local_file(self, file_path, target_lufs, audio_effects, normalize_enabled, tag_enabled, new_name=None):
        """
        Trims, normalizes, applies fades, and injects metadata on local MP3 files.
        """
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "message": "Target file not found."}
            
        try:
            normalize_audio_ffmpeg(file_path, target_lufs, audio_effects, normalize_enabled)
            
            # Executa a renomeação física do arquivo apenas se o nome mudou
            old_base = os.path.basename(file_path)
            print(f"[LIBRARY] Rename check - Old Name: '{old_base}', New Name: '{new_name}'")
            
            if new_name and old_base != new_name:
                new_file_path = os.path.join(os.path.dirname(file_path), new_name)
                print(f"[LIBRARY] Renaming physical file from '{file_path}' to '{new_file_path}'")
                
                # Never overwrite another track. A case-only rename points to the same file on Windows and is allowed
                if os.path.exists(new_file_path) and not os.path.samefile(file_path, new_file_path):
                    print(f"[LIBRARY] Rename aborted: '{new_name}' already exists in this folder.")
                    return {"success": False, "message": f"A track named '{new_name}' already exists in this folder."}

                os.rename(file_path, new_file_path)
                file_path = new_file_path  # Mantém a referência atualizada para a injeção de tags
                print(f"[LIBRARY] Rename completed successfully!")
            else:
                print(f"[LIBRARY] Rename skipped (name matches or empty new_name)")
            
            if tag_enabled:
                media_folder = _media_folder_of_track(file_path)
                if media_folder:
                    process_folder_artwork(media_folder, os.path.basename(media_folder), _artwork_config(), only_file=file_path)
                else:
                    print(f"[LIBRARY] Could not resolve the media folder of '{file_path}'. Skipping tags.")

            return {"success": True, "message": "Track processed!"}
            
        except Exception as e:
            print(f"[LIBRARY] Processing execution error: {e}")
            return {"success": False, "message": str(e)}

    def export_media_backup(self, base_path, scope, selected_folders=None):
        try:
            backup_dir = os.path.join(APP_ROOT_DIR, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"Themarr_Backup_{timestamp}.zip"
            zip_path = os.path.join(backup_dir, zip_name)
            
            library_res = self.list_local_library(base_path, scope, selected_folders)
            if not library_res.get("success"):
                return {"success": False, "message": "Nenhuma música encontrada para exportar."}
            
            library_data = library_res["library"]
            
            real_root = _library_root(base_path)
            
            written_files = 0
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for anime in library_data:
                    for track in anime["tracks"]:
                        file_path = track["file_path"]
                        if os.path.exists(file_path):
                            arcname = os.path.relpath(file_path, real_root)
                            zipf.write(file_path, arcname)
                            written_files += 1
                                    
            if written_files == 0:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                return {"success": False, "message": "Nenhum arquivo físico de áudio encontrado para backup."}
                
            return {
                "success": True, 
                "message": f"Backup exportado com sucesso contendo {written_files} música(s)!",
                "filename": zip_name
            }
        except Exception as e:
            print(f"[BACKUP] Erro ao exportar: {e}")
            return {"success": False, "message": str(e)}

    def select_backup_file(self):
        file_path = ""
        try:
            if len(webview.windows) > 0:
                active_window = next(iter(webview.windows))
                result = active_window.create_file_dialog(
                    webview.OPEN_DIALOG, 
                    file_types=('Zip files (*.zip)', 'All files (*.*)')
                )
                if result:
                    file_path = next(iter(result))
            else:
                cmd = (
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null;"
                    " $dialog = New-Object System.Windows.Forms.OpenFileDialog;"
                    " $dialog.Filter = 'Themarr Backup (*.zip)|*.zip';"
                    " $dialog.Title = 'Select Themarr Backup File';"
                    " if($dialog.ShowDialog() -eq 'OK') { $dialog.FileName }"
                )
                file_path = _powershell_dialog(cmd)
        except Exception as e:
            print(f"[BACKUP] Erro ao selecionar arquivo: {e}")
        return {"success": bool(file_path), "file_path": file_path}

    def analyze_backup(self, zip_path, base_path):
        if not zip_path or not os.path.exists(zip_path):
            return {"success": False, "message": "Arquivo de backup inválido."}
        if not base_path or not os.path.exists(base_path):
            return {"success": False, "message": "Diretório de mídias não configurado."}
            
        try:
            temp_dir = tempfile.mkdtemp(prefix="themarr_import_")
            
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
                
            real_dest_root = _library_root(base_path)
            
            backup_media_folders = []
            for item in os.listdir(temp_dir):
                if os.path.isdir(os.path.join(temp_dir, item)):
                    backup_media_folders.append(item)
                    
            missing_folders = []
            for folder in backup_media_folders:
                dest_folder_path = os.path.join(real_dest_root, folder)
                if not os.path.exists(dest_folder_path):
                    missing_folders.append(folder)
                    
            return {
                "success": True,
                "missing_folders": missing_folders,
                "temp_import_id": temp_dir,
                "media_count": len(backup_media_folders)
            }
        except Exception as e:
            print(f"[BACKUP] Erro ao analisar backup: {e}")
            return {"success": False, "message": str(e)}

    def finalize_backup_import(self, temp_import_id, base_path, decision, missing_folders):
        if not temp_import_id or not os.path.exists(temp_import_id):
            return {"success": False, "message": "Sessão de importação expirou ou é inválida."}
            
        try:
            real_dest_root = _library_root(base_path)
            
            imported_count = 0
            
            if decision == "cancel":
                shutil.rmtree(temp_import_id, ignore_errors=True)
                return {"success": True, "message": "Importação cancelada."}
                
            for folder in os.listdir(temp_import_id):
                temp_folder_path = os.path.join(temp_import_id, folder)
                if not os.path.isdir(temp_folder_path):
                    continue
                    
                dest_folder_path = os.path.join(real_dest_root, folder)
                
                if folder in missing_folders:
                    if decision in ("skip", "skip_missing"):
                        continue
                    elif decision == "create_all":
                        os.makedirs(dest_folder_path, exist_ok=True)
                        print(f"[IMPORT] Criando pasta de mídia ausente: '{folder}'")
                        
                for root, _, files in os.walk(temp_folder_path):
                    for file in files:
                        if file.lower().endswith(".mp3"):
                            src_file = os.path.join(root, file)
                            rel_subpath = os.path.relpath(src_file, temp_import_id)
                            dest_file = os.path.join(real_dest_root, rel_subpath)
                            
                            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                            
                            shutil.copy2(src_file, dest_file)
                            imported_count += 1
                                    
            shutil.rmtree(temp_import_id, ignore_errors=True)
            
            return {
                "success": True, 
                "message": f"Importação concluída! Restaurada(s) {imported_count} música(s)."
            }
        except Exception as e:
            print(f"[BACKUP] Erro ao finalizar importação: {e}")
            shutil.rmtree(temp_import_id, ignore_errors=True)
            return {"success": False, "message": str(e)}

    def scan_missing_themes(self, base_path, scope="all", selected_folders=None):
        try:
            library_res = self.list_local_library(base_path, "all", None)
            if not library_res.get("success"):
                return {"success": False, "message": library_res.get("message", "Failed to scan library.")}
                
            library_data = library_res["library"]
            missing_media = []
            
            for item in library_data:
                if len(item["tracks"]) == 0:
                    missing_media.append({
                        "folder_name": item["anime_name"],
                        "folder_path": item["folder_path"]
                    })
                    
            return {"success": True, "missing_media": missing_media}
        except Exception as e:
            print(f"[ASSISTANT] Error scanning missing themes: {e}")
            return {"success": False, "message": str(e)}

    def get_assistant_search_query(self, folder_name, folder_path=None):
        try:
            config = self.get_settings()
            jelly_url = config.get("jelly_url")
            jelly_api = config.get("jelly_api")
            
            official_name = folder_name
            series_id = None
            image_url = None
            genres = ""
            
            clean_fallback = clean_search_name(folder_name, remove_year=True)
            
            if jelly_url and jelly_api and config.get("jelly_check"):
                search_result = fetch_jellyfin_data(folder_name, jelly_url, jelly_api, folder_path=folder_path)
                if search_result.get("success"):
                    official_name = search_result.get("official_name")
                    series_id = search_result.get("series_id")
                    image_url = search_result.get("image_url")
                    genres = search_result.get("genres", "")
            
            if not official_name or official_name == folder_name:
                official_name = clean_fallback
                
            search_query = f"{official_name} official theme song opening"
            
            return {
                "success": True,
                "folder_name": folder_name,
                "official_name": official_name,
                "search_query": search_query,
                "image_url": image_url,
                "genres": genres,
                "series_id": series_id
            }
        except Exception as e:
            print(f"[ASSISTANT] Error getting search query for {folder_name}: {e}")
            return {"success": False, "message": str(e)}

    def get_media_theme_suggestions(self, folder_name, folder_path=None):
        try:
            meta = self.get_assistant_search_query(folder_name, folder_path)
            if not meta.get("success"):
                return {"success": False, "message": meta.get("message")}
                
            query = meta["search_query"]
            yt_results = self.search_youtube(query)
            top_results = yt_results[:3] if yt_results else []
            
            return {
                "success": True,
                "folder_name": folder_name,
                "official_name": meta["official_name"],
                "search_query": query,
                "image_url": meta["image_url"],
                "genres": meta["genres"],
                "series_id": meta["series_id"],
                "suggestions": top_results
            }
        except Exception as e:
            print(f"[ASSISTANT] Error getting suggestions for {folder_name}: {e}")
            return {"success": False, "message": str(e)}

    def process_assistant_downloads(self, download_list, base_folder, options=None):
        if global_state.get("is_processing", False):
            return {"success": False, "message": "Themarr is currently processing another task. Please wait."}
            
        global_state["is_processing"] = True
        global_state["percentage"] = 0
        global_state["statusText"] = "Starting Assistant Downloads..."
        global_state["percentageText"] = "0%"
        
        _start_background(self._execute_assistant_download_thread, download_list, base_folder, options or {})
        return {"success": True, "message": "Assistant download started!"}

    def _execute_assistant_download_thread(self, download_list, base_folder, options):
        try:
            current_config = self.get_settings()
            normalize_enabled = options.get("normalize", True)
            audio_effects = current_config.get("audio_fx", {}) if options.get("fades", True) else {}
            tags_enabled = options.get("tags", True)
            target_lufs = float(current_config.get("lufs", -24))
            
            total = len(download_list)
            print(f"\n[ASSISTANT] Starting batch download of {total} items...\n")
            
            for i, item in enumerate(download_list):
                folder_name = item["folder_name"]
                folder_path = item["folder_path"]
                track_name = item["track_name"]
                youtube_url = item["youtube_url"]
                
                percentage = int((i / total) * 100)
                global_state["percentage"] = percentage
                global_state["statusText"] = f"Downloading theme for: {folder_name}"
                global_state["percentageText"] = f"{i}/{total} ({percentage}%)"
                
                downloaded_file = None
                try:
                    downloaded_file = _download_with_retry(youtube_url, "[ASSISTANT]", folder_name)

                    global_state["statusText"] = f"Normalizing theme for: {folder_name}"
                    
                    final_path = generate_destination_path(
                        anime_folder=folder_path,
                        theme_type="main",
                        custom_name=track_name,
                        season_folder=None,
                        multiple_main=False
                    )
                    
                    normalize_and_save(
                        downloaded_file,
                        final_path,
                        target_lufs,
                        audio_effects,
                        normalize_enabled=normalize_enabled
                    )

                    if tags_enabled:
                        process_folder_artwork(folder_path, folder_name, _artwork_config())
                    print(f"[ASSISTANT SUCCESS] Successfully applied theme for: {folder_name}")
                    
                except Exception as e:
                    print(f"[ASSISTANT ERROR] Failed to process {folder_name}: {e}")
                    
                finally:
                    if downloaded_file and os.path.exists(downloaded_file):
                        try:
                            os.remove(downloaded_file)
                        except Exception as ex:
                            print(f"[ASSISTANT WARNING] Could not remove temp file: {ex}")
                            
            global_state["percentage"] = 100
            global_state["statusText"] = "Assistant downloads complete!"
            global_state["percentageText"] = f"{total}/{total} (100%)"
            print("\n[ASSISTANT] Batch download thread finished successfully.\n")
            
        except Exception as err:
            print(f"[ASSISTANT] Critical thread error: {err}")
            global_state["statusText"] = f"Error: {str(err)}"
        finally:
            global_state["is_processing"] = False