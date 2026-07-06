import os
import subprocess
import tempfile
import shutil
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error, TIT2, TALB, TCON

from core.config import FFMPEG_PATH

def build_audio_filter_chain(input_file, target_lufs, audio_effects, normalize_enabled=True):
    """Builds the FFmpeg filter chain based on user choices"""
    if audio_effects is None:
        audio_effects = {}
        
    filters = []
    
    if audio_effects.get("enabled", False):
        
        if audio_effects.get("remove_silence"):
            filters.append("silenceremove=start_periods=1:start_threshold=-50dB")
            
        if audio_effects.get("fade_in", 0) > 0:
            duration_in = audio_effects.get("fade_in")
            filters.append(f"afade=t=in:st=0:d={duration_in}")
            
        if audio_effects.get("fade_out", 0) > 0:
            try:
                audio = MP3(input_file)
                total_time = audio.info.length
                duration_out = audio_effects.get("fade_out")
                
                start_time = max(0, total_time - duration_out)
                filters.append(f"afade=t=out:st={start_time}:d={duration_out}")
            except Exception as e:
                print(f"[AUDIO] ⚠️ Warning: Could not apply Fade Out (Failed to read duration): {e}")

    if normalize_enabled:
        filters.append(f"loudnorm=I={target_lufs}:LRA=11:TP=-1.0")

    if not filters:
        filters.append("anull")
    
    return ",".join(filters)


def normalize_and_save(input_file, full_output_path, target_lufs, audio_effects=None):
    print(f"\n[AUDIO] Enhancing & Normalizing -> {full_output_path}")
    
    filter_chain = build_audio_filter_chain(input_file, target_lufs, audio_effects)
    
    command = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
        '-i', input_file,
        '-vn',
        '-filter:a', filter_chain, 
        '-b:a', '320k',
        full_output_path
    ]
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.run(command, check=True, startupinfo=startupinfo)
    print("[AUDIO] ✨ Success! File is treated and ready.")


def normalize_audio_ffmpeg(mp3_path, target_lufs, audio_effects=None, normalize_enabled=True):
    """Processing version for local files (Batch Mode / Enhance)"""
    temp_file = mp3_path + ".temp.mp3"
    
    filter_chain = build_audio_filter_chain(mp3_path, target_lufs, audio_effects, normalize_enabled)
    
    command = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
        '-i', mp3_path,
        '-vn',
        '-filter:a', filter_chain, 
        '-b:a', '320k',
        temp_file
    ]

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(command, check=True, startupinfo=startupinfo)
        
        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
            shutil.move(temp_file, mp3_path)
            return True
        else:
            if os.path.exists(temp_file): os.remove(temp_file)
            return False
    except Exception as e:
        print(f"[FFMPEG] ❌ Error processing {mp3_path}: {e}")
        if os.path.exists(temp_file): os.remove(temp_file)
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

def inject_mp3_metadata(mp3_path, image_path, title, album, genre):
    try:
        audio = MP3(mp3_path, ID3=ID3)
        
        if audio.tags is None:
            try:
                audio.add_tags()
            except error:
                pass 
        else:
            keys_to_remove = [key for key in audio.tags.keys() if key.startswith('APIC')]
            for key in keys_to_remove:
                audio.tags.pop(key, None)
                
        audio.tags.add(TIT2(encoding=3, text=title)) 
        audio.tags.add(TALB(encoding=3, text=album)) 
        
        if genre:
            audio.tags.add(TCON(encoding=3, text=genre)) 
        
        if image_path and os.path.exists(image_path) and os.path.getsize(image_path) > 1024:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                
            is_jpeg = image_data.startswith(b'\xff\xd8')
            is_png = image_data.startswith(b'\x89PNG')
            
            if is_jpeg or is_png:
                mime_type = 'image/png' if is_png else 'image/jpeg'
                audio.tags.add(
                    APIC(
                        encoding=3,       
                        mime=mime_type,   
                        type=3,           
                        desc=u'Cover',    
                        data=image_data 
                    )
                )
                print(f"[MP3] 🖼️ Successfully embedded artwork into: {os.path.basename(mp3_path)}")
            else:
                print(f"[MP3] ⚠️ Warning: Image {image_path} is invalid/corrupt. Skipping to avoid black covers.")
        
        audio.save(v2_version=3)
        return True
    except Exception as e:
        print(f"[MP3] ❌ Error injecting metadata: {e}")
        return False