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