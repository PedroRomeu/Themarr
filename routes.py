import os
import queue
from flask import render_template, jsonify, request

from core.logger import log_queue
from api_controller import global_state

def register_routes(app, api_system):

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
            
        from flask import send_file
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
        
        from core.config import load_config
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