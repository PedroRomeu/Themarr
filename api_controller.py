import os
import threading
import tkinter as tk
import re
import tempfile
import webview
import shutil
import requests
from tkinter import filedialog

from core.config import load_config, save_config, APP_ROOT_DIR
from core.logger import log_queue
from core.audio import download_music, normalize_and_save, normalize_audio_ffmpeg, inject_mp3_metadata
from core.jellyfin import fetch_jellyfin_data, download_jellyfin_image, fetch_jellyfin_season_image
from core.files import generate_destination_path, move_loose_episodes

global_state = {
    "is_processing": False,
    "percentage": 0,
    "statusText": "Ready",
    "percentageText": "0%",
    "item_statuses": [] 
}

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
        if os.path.exists(test_path) and os.path.getsize(test_path) > 1024:
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
            audio_effects = current_config.get("audio_fx", {})
            
            for anime_folder in folders_to_process:
                anime_name = os.path.basename(anime_folder)
                
                if options.get("organize", True):
                    self._auto_organize_single_season(anime_folder)
                
                if not options.get("normalize", True) and not options.get("metadata", True) and not options.get("audio_fx", False):
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

        current_config = self.get_settings()
        audio_effects = current_config.get("audio_fx", {})
        
        link = music['link']
        name = music.get('name', music.get('nome'))
        destination = music.get('destination', music.get('destino'))
        lufs = music['lufs']
        has_multi_main = music.get('has_multi_main', False)

        track_fx = music.get('audio_fx') or audio_effects
        
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
            normalize_and_save(downloaded_file, final_path, lufs, track_fx)
            
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

        current_config = self.get_settings()
        audio_effects = current_config.get("audio_fx", {})

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

            track_fx = music.get('audio_fx') or audio_effects
            
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
                normalize_and_save(downloaded_file, final_path, lufs, track_fx)
                
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