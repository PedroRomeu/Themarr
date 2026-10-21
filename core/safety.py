"""Media safety guard for server mode.

On the server the media folders belong to Jellyfin and nothing there may ever be lost. In server mode
Themarr may only write, rename or delete theme files: <media>/theme.mp3 and
<media>/[<season>/]theme-music/*.mp3, inside MEDIA_ROOT. It never creates a media folder; a season
folder may be created inside an existing media folder (queue and Organize do that, like on desktop).
Organize moves episodes through core.files.safe_move, which never replaces an existing file.

Desktop mode keeps the original behavior: every check here is a no-op unless SERVER_MODE is on.
"""
import os

from core.config import SERVER_MODE, MEDIA_ROOT


class UnsafeMediaOperation(PermissionError):
    pass


def is_within_media_root(path):
    if not SERVER_MODE:
        return True
    try:
        real = os.path.realpath(path)
        return os.path.commonpath([real, MEDIA_ROOT]) == MEDIA_ROOT
    except ValueError:
        return False


def is_theme_file(path):
    name = os.path.basename(path).lower()
    parent = os.path.basename(os.path.dirname(path)).lower()
    return name.endswith('.mp3') and (name == 'theme.mp3' or parent == 'theme-music')


def is_season_folder_name(name):
    name = name.lower()
    return "season" in name or "temporada" in name or name == "specials"


def theme_owner_folder(path):
    """Media or season folder that holds a theme file (must already exist on disk)"""
    parent = os.path.dirname(path)
    return os.path.dirname(parent) if os.path.basename(parent).lower() == 'theme-music' else parent


def check_theme_write(path, action="write"):
    """Raises UnsafeMediaOperation when server mode would touch anything other than a theme file"""
    if not SERVER_MODE:
        return
    if not is_within_media_root(path):
        raise UnsafeMediaOperation(f"Blocked {action} outside the media folder: {path}")
    if not is_theme_file(path):
        raise UnsafeMediaOperation(f"Blocked {action} of a non-theme file: {path}")
    owner = theme_owner_folder(path)
    # <MEDIA_ROOT>/<library>/<media>[/<season>]: never the root or a library folder such as /data/Animes
    depth = len(os.path.relpath(os.path.realpath(owner), MEDIA_ROOT).split(os.sep))
    if depth < 2:
        raise UnsafeMediaOperation(f"Blocked {action}: '{owner}' is not a media or season folder")
    if not os.path.isdir(owner):
        # A missing season folder may be created, but only inside an existing media folder
        new_season = depth == 3 and is_season_folder_name(os.path.basename(owner)) and os.path.isdir(os.path.dirname(owner))
        if not new_season:
            raise UnsafeMediaOperation(f"Blocked {action}: '{owner}' is not an existing media or season folder")


def check_media_read(path):
    """Server mode only reads inside the media folder"""
    if SERVER_MODE and not is_within_media_root(path):
        raise UnsafeMediaOperation(f"Blocked access outside the media folder: {path}")


def theme_files_only(paths):
    """In server mode, drops every path that is not a theme file (other MP3s, soundtracks, ...)"""
    return [p for p in paths if is_theme_file(p)] if SERVER_MODE else list(paths)
