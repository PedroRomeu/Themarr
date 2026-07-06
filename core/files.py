import os
import re
import shutil

def clean_search_name(folder_name, remove_year=False):
    if folder_name.lower().endswith('.mp3'):
        folder_name = os.path.splitext(folder_name)[0]
        
    clean_name = folder_name.replace('：', ' ').replace('-', ' ')
    
    if remove_year:
        clean_name = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', clean_name)
    else:
        clean_name = re.sub(r'\[.*?\]|\{.*?\}', '', clean_name)
    
    clean_name = clean_name.replace('...', ' ')
    clean_name = re.sub(r"[.,\/#!$%\^&\*;:{}=\-_`~()'’]", ' ', clean_name)
    
    clean_name = re.sub(r'\s+', ' ', clean_name)
    return clean_name.strip()

def generate_destination_path(anime_folder, theme_type, custom_name, season_folder=None, multiple_main=False):
    if not custom_name.endswith('.mp3'):
        custom_name += '.mp3'
        
    if theme_type == 'temporada' or theme_type == 'season':
        final_folder = os.path.join(anime_folder, season_folder, 'theme-music')
        final_file = os.path.join(final_folder, custom_name)
    elif theme_type == 'main':
        theme_music_folder = os.path.join(anime_folder, 'theme-music')
        loose_theme_file = os.path.join(anime_folder, 'theme.mp3')
        
        if multiple_main or os.path.isdir(theme_music_folder):
            final_folder = theme_music_folder
            final_file = os.path.join(final_folder, custom_name)
            
        elif os.path.exists(loose_theme_file):
            os.makedirs(theme_music_folder, exist_ok=True)
            shutil.move(loose_theme_file, os.path.join(theme_music_folder, 'theme.mp3'))
            print("[SYSTEM] Migrated existing 'theme.mp3' to 'theme-music' folder to support multiple themes.")
            
            final_folder = theme_music_folder
            final_file = os.path.join(final_folder, custom_name)
            
        else:
            final_folder = anime_folder
            final_file = os.path.join(final_folder, 'theme.mp3')
    else:
        raise ValueError("Theme type must be 'main' or 'season'.")

    os.makedirs(final_folder, exist_ok=True)
    return final_file

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