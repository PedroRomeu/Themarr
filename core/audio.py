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


def normalize_and_save(input_file, full_output_path, target_lufs, audio_effects=None, start_time=None, end_time=None):
    dir_name, file_name = os.path.split(full_output_path)
    
    forbidden_chars = ['|', '*', '?', ':', '"', '<', '>', '/', '\\']
    for char in forbidden_chars:
        file_name = file_name.replace(char, '-') 
        
    while '  ' in file_name:
        file_name = file_name.replace('  ', ' ')
        
    full_output_path = os.path.join(dir_name, file_name)
    
    print(f"\n[AUDIO] Enhancing & Normalizing -> {full_output_path}")
    
    ss_sec = parse_time_to_seconds(start_time)
    to_sec = parse_time_to_seconds(end_time)
    
    if ss_sec is not None:
        print(f"[AUDIO] Trim Start Configured: {ss_sec}s")
    if to_sec is not None:
        print(f"[AUDIO] Trim End Configured: {to_sec}s")

    if audio_effects is None:
        audio_effects = {}
    else:
        audio_effects = dict(audio_effects)
        
    if ss_sec is not None or to_sec is not None:
        audio_effects['remove_silence'] = False
        print("[AUDIO] Manual trim active: forcing 'remove_silence' to False to prevent timeline shifting.")

    temp_trimmed_file = None
    
    if ss_sec is not None or to_sec is not None:
        print("[AUDIO] ✂️ Applying pre-trim to audio file before applying effects...")
        try:
            ext = os.path.splitext(input_file)[1] or '.mp3'
            fd, temp_trimmed_file = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            
            trim_cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y']
            
            if ss_sec is not None:
                trim_cmd += ['-ss', str(ss_sec)]
                
            if to_sec is not None:
                start_offset = ss_sec if ss_sec is not None else 0.0
                duration = to_sec - start_offset
                trim_cmd += ['-t', str(duration)]
            
            trim_cmd += ['-i', input_file, '-codec:a', 'libmp3lame', '-b:a', '320k', temp_trimmed_file]
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(trim_cmd, check=True, startupinfo=startupinfo)
            
            input_file = temp_trimmed_file
            print("[AUDIO] Pre-trim applied successfully with reset timestamps!")
            
        except Exception as trim_err:
            print(f"[AUDIO] Critical Error during pre-trim: {trim_err}")
            if temp_trimmed_file and os.path.exists(temp_trimmed_file):
                try:
                    os.remove(temp_trimmed_file)
                except:
                    pass
            raise trim_err

    try:
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
        print("[AUDIO] ✨ Success! File is treated, trimmed, normalized and ready.")
        
    finally:
        if temp_trimmed_file and os.path.exists(temp_trimmed_file):
            try:
                os.remove(temp_trimmed_file)
                print("[AUDIO] Cleaned up temporary trim files.")
            except Exception as cleanup_err:
                print(f"[AUDIO] Warning: Could not remove temp file: {cleanup_err}")


def normalize_audio_ffmpeg(mp3_path, target_lufs, audio_effects=None, normalize_enabled=True):
    """
    Processing version for local files (Batch Mode / Enhance) with in-place saving
    """
    if audio_effects is None:
        audio_effects = {}

    start_time = audio_effects.get("start_time")
    end_time = audio_effects.get("end_time")

    ss_sec = parse_time_to_seconds(start_time)
    to_sec = parse_time_to_seconds(end_time)

    dir_name, file_name = os.path.split(mp3_path)
    temp_output = os.path.join(dir_name, f"temp_proc_{file_name}")
    
    input_file = mp3_path
    temp_trimmed_file = None

    if ss_sec is not None or to_sec is not None:
        try:
            ext = os.path.splitext(input_file)[1] or '.mp3'
            fd, temp_trimmed_file = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            
            trim_cmd = [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y']
            
            if ss_sec is not None:
                trim_cmd += ['-ss', str(ss_sec)]
                
            if to_sec is not None:
                start_offset = ss_sec if ss_sec is not None else 0.0
                duration = to_sec - start_offset
                trim_cmd += ['-t', str(duration)]
            
            trim_cmd += ['-i', input_file, '-codec:a', 'libmp3lame', '-b:a', '320k', temp_trimmed_file]
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.run(trim_cmd, check=True, startupinfo=startupinfo)
            input_file = temp_trimmed_file
            
        except Exception as trim_err:
            print(f"[AUDIO] Error during local pre-trim: {trim_err}")
            if temp_trimmed_file and os.path.exists(temp_trimmed_file):
                try: os.remove(temp_trimmed_file)
                except: pass
            raise trim_err

    try:
        filter_chain = build_audio_filter_chain(input_file, target_lufs, audio_effects, normalize_enabled)
        
        command = [
            FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
            '-i', input_file,
            '-vn',
            '-filter:a', filter_chain, 
            '-b:a', '320k',
            temp_output
        ]
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        subprocess.run(command, check=True, startupinfo=startupinfo)
        
        if os.path.exists(temp_output):
            shutil.move(temp_output, mp3_path)
            
    finally:
        if temp_trimmed_file and os.path.exists(temp_trimmed_file):
            try: os.remove(temp_trimmed_file)
            except: pass
        if os.path.exists(temp_output):
            try: os.remove(temp_output)
            except: pass

def parse_time_to_seconds(time_str):
    """Convert time strings like '5', '0:05', '1:08' ou '01:08' in pure seconds (float/int)"""
    if not time_str:
        return None
    time_str = str(time_str).strip()
    if not time_str:
        return None
    
    if time_str.replace('.', '', 1).isdigit():
        return float(time_str)
        
    parts = time_str.split(':')
    try:
        if len(parts) == 2:  
            min_str, sec_str = parts
            return int(min_str) * 60 + float(sec_str)
            
        elif len(parts) == 3:  
            hr_str, min_str, sec_str = parts
            return int(hr_str) * 3600 + int(min_str) * 60 + float(sec_str)
            
    except (ValueError, IndexError):
        pass
    return None


def get_streaming_url(youtube_url):
    """Extract the direct audio URL from YouTube and the total duration in seconds (without downloading anything)"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'force_generic_extractor': False
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return {
                "success": True,
                "url": info.get('url'),
                "duration": info.get('duration')  # Duração total em segundos
            }
    except Exception as e:
        print(f"[AUDIO] Erro ao extrair stream do YouTube: {e}")
        return {"success": False, "error": str(e)}

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