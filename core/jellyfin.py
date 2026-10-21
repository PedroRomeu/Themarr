import os
import re
import threading
import time
import requests

from core.files import clean_search_name

LIBRARY_INDEX_TTL = 600  # seconds before the series/movie list is fetched again

_index_lock = threading.Lock()
_index_cache = {}  # (url, api_key) -> (timestamp, index)


def _path_parts(path):
    """Folder components of a path, lower-cased, accepting both / and \\ separators"""
    return [p.casefold() for p in re.split(r'[\\/]+', str(path).strip()) if p]


def _item_result(item, clean_url):
    genres_list = item.get("Genres", [])
    return {
        "success": True,
        "official_name": item.get("Name"),
        "series_id": item.get("Id"),
        "image_url": f"{clean_url}/Items/{item.get('Id')}/Images/Primary?format=jpg",
        "genres": ", ".join(genres_list) if genres_list else ""
    }


def _build_library_index(items):
    """Maps each media folder of the Jellyfin library to its item. Series point to their folder; movies to the folder holding the file"""
    entries = []
    movie_dirs = {}

    for item in items:
        path = item.get("Path")
        if not path:
            continue
        if item.get("Type") == "Movie":
            folder = re.split(r'[\\/]+', path.rstrip('\\/'))[:-1]
            folder_path = "/".join(folder)
            movie_dirs[folder_path.casefold()] = movie_dirs.get(folder_path.casefold(), 0) + 1
        else:
            folder_path = path
        entries.append((folder_path, item))

    index = []
    for folder_path, item in entries:
        # Movies stored loose in a shared folder have no folder of their own to match
        if item.get("Type") == "Movie" and movie_dirs.get(folder_path.casefold(), 0) > 1:
            continue
        parts = _path_parts(folder_path)
        if parts:
            index.append((parts, folder_path, item))
    return index


def get_library_index(jellyfin_url, api_key, force_refresh=False):
    """Series and movies of the Jellyfin library with their paths, cached for LIBRARY_INDEX_TTL seconds. Empty list when unreachable"""
    clean_url = jellyfin_url.rstrip('/')
    key = (clean_url, api_key)

    with _index_lock:
        cached = _index_cache.get(key)
        if cached and not force_refresh and time.time() - cached[0] < LIBRARY_INDEX_TTL:
            return cached[1]

        try:
            res = requests.get(
                f"{clean_url}/Items",
                headers={"X-Emby-Token": api_key},
                params={"IncludeItemTypes": "Series,Movie", "Recursive": "true", "Fields": "Path,Genres"},
                timeout=20
            )
            if res.status_code != 200:
                print(f"[JELLYFIN] ⚠️ Could not load the library index (status {res.status_code}). Using name search.")
                return []
            index = _build_library_index(res.json().get("Items", []))
        except Exception as e:
            print(f"[JELLYFIN] ⚠️ Could not load the library index: {e}. Using name search.")
            return []

        _index_cache[key] = (time.time(), index)
        print(f"[JELLYFIN] 📚 Library index loaded: {len(index)} media folder(s).")
        return index


def match_media_folder(index, folder):
    """Item whose media folder is `folder` (a full path or just the folder name). Compares from the end of the path, so
    D:\\Medias\\Animes\\X and /data/Animes/X match each other. Returns None when nothing or more than one item fits"""
    target = _path_parts(folder)
    if not target:
        return None

    candidates = [entry for entry in index if entry[0][-1] == target[-1]]
    depth = 2
    while len(candidates) > 1 and depth <= len(target):
        candidates = [entry for entry in candidates if entry[0][-depth:] == target[-depth:]]
        depth += 1

    return candidates[0][2] if len(candidates) == 1 else None


def find_jellyfin_item(item_id, jellyfin_url, api_key):
    """Looks up one item by id. Seasons and episodes resolve to their series"""
    clean_url = jellyfin_url.rstrip('/')
    headers = {"X-Emby-Token": api_key}
    try:
        res = requests.get(f"{clean_url}/Items", headers=headers,
                           params={"Ids": item_id, "Recursive": "true", "Fields": "Path,Genres"}, timeout=10)
        items = res.json().get("Items", []) if res.status_code == 200 else []

        # Jellyfin ignores an invalid Ids filter and returns other items, so only the requested id is accepted
        wanted = str(item_id).replace("-", "").casefold()
        item = next((i for i in items if str(i.get("Id", "")).replace("-", "").casefold() == wanted), None)
        if not item:
            return None
        if item.get("Type") in ("Season", "Episode") and item.get("SeriesId"):
            return find_jellyfin_item(item["SeriesId"], jellyfin_url, api_key)
        return item if item.get("Type") in ("Series", "Movie") else None
    except Exception as e:
        print(f"[JELLYFIN] ❌ Error looking up item {item_id}: {e}")
        return None


def fetch_jellyfin_data(folder_name, jellyfin_url, api_key, folder_path=None):
    clean_url = jellyfin_url.rstrip('/')
    headers = {"X-Emby-Token": api_key}

    # STEP 0: Exact match by folder path against the library index
    item = match_media_folder(get_library_index(jellyfin_url, api_key), folder_path or folder_name)
    if item:
        print(f"[JELLYFIN] ✅ Matched by folder path: {item.get('Name')}")
        return _item_result(item, clean_url)

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
                        "image_url": f"{clean_url}/Items/{series.get('Id')}/Images/Primary?format=jpg",
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

    # STEP 3: Significant Word Search (Smarter Fallback)
    words = generic_term.split()
    
    significant_words = [w for w in words if len(w) > 3]
    
    if len(significant_words) > 0:
        broad_term = significant_words[0]
        print(f"[JELLYFIN] ⚠️ Not found. Trying Broad Search: '{broad_term}'...")
        result = try_search(broad_term)
        if result["success"]:
            print(f"[JELLYFIN] ✅ Found via Broad Search: {result['official_name']}")
            return result
        
        if len(significant_words) > 1:
            broad_term_2 = f"{significant_words[0]} {significant_words[1]}"
            print(f"[JELLYFIN] ⚠️ Not found. Trying Ultra Broad Search: '{broad_term_2}'...")
            result = try_search(broad_term_2)
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
            content_type = res.headers.get('Content-Type', '').lower()
            if 'text' in content_type or 'html' in content_type:
                print(f"[JELLYFIN] ❌ Failed: Server returned HTML/text instead of an image. Auth/URL issue?")
                return None
                
            os.makedirs(dest_folder, exist_ok=True)
            with open(full_path, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if os.path.exists(full_path) and os.path.getsize(full_path) > 1024:
                print(f"[JELLYFIN] 💾 Image saved successfully at: {full_path}")
                return full_path
            else:
                if os.path.exists(full_path): os.remove(full_path)
                return None
        else:
            print(f"[JELLYFIN] ❌ Failed to download image. Status: {res.status_code}")
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
                        return f"{clean_url}/Items/{season_id}/Images/Primary?format=jpg"
    except Exception as e:
        print(f"[JELLYFIN] ❌ Error fetching season {season_num} data: {e}")
    return None