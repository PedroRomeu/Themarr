import os
import requests

from core.files import clean_search_name

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