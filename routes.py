import os
import re
import time
from datetime import timedelta

from flask import render_template, jsonify, request, send_file, session, redirect, url_for

from core.config import load_config, SERVER_MODE, MEDIA_ROOT, BACKUP_DIR
from core.safety import UnsafeMediaOperation, check_media_read, check_theme_write, is_theme_file
from api_controller import save_uploaded_backup

PUBLIC_ENDPOINTS = {'login', 'static'}


def _safe_next(target):
    """Only same-site paths are accepted after login"""
    return target if target and target.startswith('/') and not target.startswith('//') else '/'


def register_auth(app):
    """Server mode: every page and API call needs a signed-in Jellyfin administrator"""
    from core.auth import get_secret_key, authenticate_jellyfin_admin

    app.secret_key = get_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,  # backup uploads
    )

    @app.before_request
    def require_login():
        if request.endpoint in PUBLIC_ENDPOINTS or session.get('user'):
            return None
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "status": "error", "message": "Login required."}), 401
        return redirect(url_for('login', next=request.full_path.rstrip('?')))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        next_url = _safe_next(request.values.get('next', '/'))
        if request.method == 'GET':
            return render_template('login.html', error=None, next_url=next_url)

        result = authenticate_jellyfin_admin(request.form.get('username', '').strip(), request.form.get('password', ''))
        if not result["ok"]:
            time.sleep(1)  # slows down password guessing
            print(f"[AUTH] Failed login for '{request.form.get('username', '')}': {result['message']}")
            return render_template('login.html', error=result["message"], next_url=next_url), 401

        session.permanent = True
        session['user'] = result["name"]
        print(f"[AUTH] {result['name']} signed in.")
        return redirect(next_url)

    @app.route('/logout', methods=['POST'])
    def logout():
        session.clear()
        return redirect(url_for('login'))

def register_routes(app, api_system):
    if SERVER_MODE:
        register_auth(app)

    @app.errorhandler(UnsafeMediaOperation)
    def blocked_media_operation(error):
        print(f"[SAFETY] 🛡️ {error}")
        return jsonify({"success": False, "status": "error", "message": str(error)}), 403

    @app.route('/api/app_info', methods=['GET'])
    def api_flask_app_info():
        return jsonify({"server_mode": SERVER_MODE, "media_root": MEDIA_ROOT, "user": session.get('user') if SERVER_MODE else None})

    @app.route('/api/browse_folders', methods=['POST'])
    def api_flask_browse_folders():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(api_system.browse_media_folders(data.get('folder')))

    @app.route('/api/suggest_folders', methods=['POST'])
    def api_flask_suggest_folders():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(api_system.suggest_media_folders(data.get('text', '')))

    @app.route('/api/select_server_folder', methods=['POST'])
    def api_flask_select_server_folder():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(api_system.select_server_folder(data.get('folder', '')))

    @app.route('/api/library/backup/upload', methods=['POST'])
    def api_flask_upload_backup():
        upload = request.files.get('file')
        if not upload or not upload.filename.lower().endswith('.zip'):
            return jsonify({"success": False, "message": "Please choose a .zip backup file."})
        return jsonify({"success": True, "file_path": save_uploaded_backup(upload)})

    @app.route('/api/library/backup/download')
    def api_flask_download_backup():
        name = os.path.basename(request.args.get('name', ''))
        path = os.path.join(BACKUP_DIR, name)
        if not re.fullmatch(r'Themarr_Backup_\d{8}_\d{6}\.zip', name) or not os.path.isfile(path):
            return "Backup not found", 404
        return send_file(path, as_attachment=True, download_name=name)

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
        queue_data = data.get('queue', [])
        folder = data.get('folder', '')
        api_system.process_queue(queue_data, folder)
        return jsonify({"status": "success"})

    @app.route('/api/get_subfolders', methods=['POST'])
    def api_flask_get_subfolders():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(api_system.get_subfolders(data.get('folder', '')))

    @app.route('/api/jellyfin/resolve_item', methods=['POST'])
    def api_flask_resolve_jellyfin_item():
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(api_system.resolve_jellyfin_item(data.get('item_id', '')))

    @app.route('/api/status', methods=['GET'])
    def api_flask_status():
        return jsonify(api_system.get_status())

    @app.route('/api/test_jellyfin', methods=['POST'])
    def api_flask_test_jellyfin():
        try:
            data = request.get_json(force=True, silent=True) or {}
            
            url = data.get('url', '')
            api_key = data.get('api_key', data.get('api', '')) 
            
            print(f"\n[RECEIVED FROM BROWSER] URL: {url} | API: {'*' * 8 if api_key else '(empty)'}")
            
            result = api_system.test_jellyfin(url, api_key)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"status": "error", "message": f"❌ Flask Route Error: {str(e)}"})
        
    @app.route('/api/delete_music_folder', methods=['POST'])
    def api_flask_delete_music():
        try:
            data = request.get_json(force=True, silent=True) or {}
            folder = data.get('folder', '')
            scope = data.get('scope', 'single')
            selected_folders = data.get('selectedFolders', [])

            print(f"\n[RECEIVED FROM BROWSER] Delete files in: {folder} | Scope: {scope}")

            result = api_system.delete_music_folder(folder, scope, selected_folders)
            return jsonify(result)
            
        except Exception as e:
            print(f"[FLASK ERROR] Delete failed: {e}")
            return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"})

    @app.route('/api/enhance_local_music', methods=['POST'])
    def api_flask_enhance_music():
        try:
            data = request.get_json(force=True, silent=True) or {}
            
            folder = data.get('folder', '')
            scope = data.get('scope', 'single')
            lufs = data.get('lufs', '-24')
            options = data.get('options', None)
            selected_folders = data.get('selectedFolders', [])

            print(f"\n[RECEIVED FROM BROWSER] Enhance - Folder: {folder} | Scope: {scope} | LUFS: {lufs} | Options: {options}")

            result = api_system.enhance_local_music(folder, scope, lufs, options, selected_folders)
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
        
    @app.route('/api/search_youtube', methods=['POST'])
    def api_flask_search_youtube():
        try:
            data = request.get_json(force=True, silent=True) or {}
            query = data.get('query', '')
            
            print(f"\n[RECEIVED FROM BROWSER] YouTube Search Query: {query}")
            
            result = api_system.search_youtube(query)
            return jsonify(result)
            
        except Exception as e:
            print(f"[FLASK ERROR] YouTube Search failed: {e}")
            return jsonify([])

    @app.route('/api/get_stream_info', methods=['POST'])
    def get_stream_info():
        data = request.json or {}
        url = data.get('url')
        result = api_system.get_stream_info(url)
        return jsonify(result)

    @app.route('/api/library/list', methods=['POST'])
    def get_local_library():
        data = request.json or {}
        base_path = data.get('base_path', '')
        scope = data.get('scope', 'all')
        selected_folders = data.get('selected_folders', [])
        
        result = api_system.list_local_library(base_path, scope, selected_folders)
        return jsonify(result)

    @app.route('/api/library/stream')
    def stream_local_file():
        file_path = request.args.get('path')
        if not file_path or not os.path.exists(file_path):
            return "File not found", 404
        if SERVER_MODE and not is_theme_file(file_path):
            return "Only theme files can be streamed", 403
        check_media_read(file_path)

        return send_file(file_path, mimetype="audio/mpeg")

    @app.route('/api/library/process', methods=['POST'])
    def process_library_track():
        data = request.json or {}
        file_path = data.get('file_path', '')
        new_name = data.get('new_name', '')
        normalize = data.get('normalize', True)
        fades = data.get('fades', True)
        tag = data.get('tag', True)
        start_time = data.get('startTime', '')
        end_time = data.get('endTime', '')

        config = load_config()
        target_lufs = float(config.get('lufs', -24))
        
        audio_effects = {
            "enabled": fades,
            "remove_silence": False if (start_time or end_time) else config.get('audio_fx', {}).get('remove_silence', False),
            "fade_in": float(config.get('audio_fx', {}).get('fade_in', 0)) if fades else 0,
            "fade_out": float(config.get('audio_fx', {}).get('fade_out', 0)) if fades else 0,
            "start_time": start_time if start_time else None,
            "end_time": end_time if end_time else None
        }
        
        result = api_system.process_local_file(
            file_path=file_path,
            target_lufs=target_lufs,
            audio_effects=audio_effects,
            normalize_enabled=normalize,
            tag_enabled=tag,
            new_name=new_name
        )
        return jsonify(result)

    @app.route('/api/library/delete', methods=['POST'])
    def delete_library_track():
        data = request.json or {}
        file_path = data.get('file_path', '')
        if not file_path or not os.path.exists(file_path):
            return jsonify({"success": False, "message": "File not found."})

        check_theme_write(file_path, "delete")
        try:
            os.remove(file_path)
            return jsonify({"success": True, "message": "File deleted."})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route('/api/library/backup/export', methods=['POST'])
    def api_flask_export_backup():
        try:
            data = request.get_json(force=True, silent=True) or {}
            base_path = data.get('base_path', '')
            scope = data.get('scope', 'all')
            selected_folders = data.get('selected_folders', [])
            
            result = api_system.export_media_backup(
                base_path=base_path,
                scope=scope,
                selected_folders=selected_folders
            )
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Export failed: {e}")
            return jsonify({"success": False, "message": f"Erro no servidor Flask: {str(e)}"})

    @app.route('/api/library/backup/select_file', methods=['POST'])
    def api_flask_select_backup_file():
        try:
            result = api_system.select_backup_file()
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Select backup file failed: {e}")
            return jsonify({"success": False, "file_path": ""})

    @app.route('/api/library/backup/analyze', methods=['POST'])
    def api_flask_analyze_backup():
        try:
            data = request.get_json(force=True, silent=True) or {}
            zip_path = data.get('zip_path', '')
            base_path = data.get('base_path', '')
            
            result = api_system.analyze_backup(
                zip_path=zip_path,
                base_path=base_path
            )
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Analyze backup failed: {e}")
            return jsonify({"success": False, "message": f"Erro no servidor Flask: {str(e)}"})

    @app.route('/api/library/backup/finalize', methods=['POST'])
    def api_flask_finalize_backup():
        try:
            data = request.get_json(force=True, silent=True) or {}
            temp_import_id = data.get('temp_import_id', '')
            base_path = data.get('base_path', '')
            decision = data.get('decision', 'cancel')
            missing_folders = data.get('missing_folders', [])
            
            result = api_system.finalize_backup_import(
                temp_import_id=temp_import_id,
                base_path=base_path,
                decision=decision,
                missing_folders=missing_folders
            )
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Finalize backup failed: {e}")
            return jsonify({"success": False, "message": f"Erro no servidor Flask: {str(e)}"})

    @app.route('/api/library/assistant/scan', methods=['POST'])
    def api_flask_assistant_scan():
        try:
            data = request.json or {}
            base_path = data.get('base_path', '')
            scope = data.get('scope', 'all')
            selected_folders = data.get('selected_folders', [])
            result = api_system.scan_missing_themes(base_path, scope, selected_folders)
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Assistant scan failed: {e}")
            return jsonify({"success": False, "message": f"❌ Server Error: {str(e)}"})

    @app.route('/api/library/assistant/suggestions', methods=['POST'])
    def api_flask_assistant_suggestions():
        try:
            data = request.json or {}
            folder_name = data.get('folder_name', '')
            result = api_system.get_media_theme_suggestions(folder_name, data.get('folder_path'))
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Assistant suggestions failed: {e}")
            return jsonify({"success": False, "message": f"❌ Server Error: {str(e)}"})

    @app.route('/api/library/assistant/download', methods=['POST'])
    def api_flask_assistant_download():
        try:
            data = request.json or {}
            download_list = data.get('download_list', [])
            base_folder = data.get('base_folder', '')
            options = data.get('options', {})
            result = api_system.process_assistant_downloads(download_list, base_folder, options)
            return jsonify(result)
        except Exception as e:
            print(f"[FLASK ERROR] Assistant download failed: {e}")
            return jsonify({"success": False, "message": f"❌ Server Error: {str(e)}"})