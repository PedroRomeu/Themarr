import webview
from flask import Flask, render_template, jsonify, request
import threading
import sys
import os
import yt_dlp
import subprocess
import shutil
import json
import queue
import requests
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Manda o Flask silenciar as mensagens de "GET /api/logs"

# Inicia o servidor Flask (Backend)
app = Flask(__name__)

# --- 1. REINTEGRANDO SEU MOTOR DE LOGS ANTIGO ---
fila_logs = queue.Queue()

class RedirecionadorLog:
    def __init__(self, terminal_original):
        self.terminal = terminal_original
        self.capturar = False # <-- COMEÇA DESLIGADO PARA IGNORAR O LIXO INICIAL

    def write(self, texto):
        if self.terminal:
            self.terminal.write(texto)
            self.terminal.flush()
        
        # Só manda para a interface web se a captura estiver ligada
        if self.capturar:
            texto_limpo = texto.replace('\r', '\n')
            if texto_limpo:
                fila_logs.put(texto_limpo)

    def flush(self):
        if self.terminal:
            self.terminal.flush()

# --- 2. REINTEGRANDO CONFIGURAÇÕES E CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(BASE_DIR, 'bin', 'ffmpeg.exe')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# ==========================================
# FUNÇÕES DE MEMÓRIA (CONFIGURAÇÕES)
# ==========================================
def carregar_config():
    padrao = {"lufs": "-24", "jelly_check": False, "jelly_url": "", "jelly_api": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                # Atualiza os padrões com o que existir no arquivo antigo
                for chave in dados:
                    if chave in padrao:
                        padrao[chave] = dados[chave]
        except Exception as e:
            print(f"Erro ao ler config: {e}")
    return padrao

def salvar_config(dados):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")

# --- 3. REINTEGRANDO SUAS FUNÇÕES DE DOWNLOAD E CONVERSÃO ---
def baixar_musica(url_youtube):
    print(f"\n[1] Iniciando o download: {url_youtube}")
    configuracoes = {
        'format': 'bestaudio/best',
        'ffmpeg_location': FFMPEG_PATH,
        'extractor_args': {'youtube': {'client': ['android']}},
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
        'outtmpl': '%(title)s.%(ext)s',
        'nocolor': True,
    }
    with yt_dlp.YoutubeDL(configuracoes) as ydl:
        info = ydl.extract_info(url_youtube, download=True)
        nome_arquivo_base = ydl.prepare_filename(info)
        arquivo_mp3 = os.path.splitext(nome_arquivo_base)[0] + '.mp3'
    return arquivo_mp3

def gerar_caminho_destino(pasta_anime, tipo_tema, nome_customizado, pasta_temporada=None, multiplos_main=False):
    if not nome_customizado.endswith('.mp3'):
        nome_customizado += '.mp3'
    if tipo_tema == 'temporada':
        pasta_final = os.path.join(pasta_anime, pasta_temporada, 'theme-music')
        arquivo_final = os.path.join(pasta_final, nome_customizado)
    elif tipo_tema == 'main':
        if not multiplos_main:
            pasta_final = pasta_anime
            arquivo_final = os.path.join(pasta_final, 'theme.mp3')
        else:
            pasta_final = os.path.join(pasta_anime, 'theme-music')
            arquivo_final = os.path.join(pasta_final, nome_customizado)
    else:
        raise ValueError("O tipo_tema deve ser 'main' ou 'temporada'.")

    if not os.path.exists(pasta_final):
        os.makedirs(pasta_final)
    return arquivo_final

def normalizar_e_salvar(arquivo_entrada, caminho_saida_completo, volume_lufs):
    print(f"\n[2] Normalizando (Target: {volume_lufs} LUFS) em: {caminho_saida_completo}")
    comando = [
        FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
        '-i', arquivo_entrada, '-filter:a', f'loudnorm=I={volume_lufs}:LRA=11:TP=-1.0', '-b:a', '320k',
        caminho_saida_completo
    ]
    subprocess.run(comando, check=True)
    print("Sucesso! Arquivo pronto e no lugar certo.")

def mover_episodios_soltos(pasta_raiz, pasta_temporada):
    extensoes_media = ('.mkv', '.mp4', '.avi', '.ass', '.srt', '.vtt')
    caminho_temp = os.path.join(pasta_raiz, pasta_temporada)
    if not os.path.exists(caminho_temp):
        os.makedirs(caminho_temp)
    arquivos_movidos = 0
    for arquivo in os.listdir(pasta_raiz):
        caminho_arquivo = os.path.join(pasta_raiz, arquivo)
        if os.path.isfile(caminho_arquivo) and arquivo.lower().endswith(extensoes_media):
            caminho_novo = os.path.join(caminho_temp, arquivo)
            shutil.move(caminho_arquivo, caminho_novo)
            arquivos_movidos += 1
    if arquivos_movidos > 0:
        print(f"\n[!] Faxina Inteligente: {arquivos_movidos} arquivo(s) de mídia movidos!")


# =======================================================
# ROTAS DO FLASK (COMO O FRONTEND VAI ACESSAR O BACKEND)
# =======================================================

@app.route('/')
def home():
    return render_template('index.html')

# Nova rota para enviar os logs do terminal em tempo real para o HTML
@app.route('/api/logs')
def obter_logs():
    logs = []
    try:
        while not fila_logs.empty():
            logs.append(fila_logs.get_nowait())
    except queue.Empty:
        pass
    return jsonify({"logs": "".join(logs)})

# =======================================================
# PONTE DE COMUNICAÇÃO JS -> PYTHON (A CLASSE API)
# =======================================================
class Api:
    def selecionar_pasta(self):
        resultado = janela.create_file_dialog(webview.FOLDER_DIALOG)
        if resultado:
            pasta = resultado[0]
            temporadas = []
            try:
                for item in os.listdir(pasta):
                    if os.path.isdir(os.path.join(pasta, item)) and item != "theme-music":
                        temporadas.append(item)
            except Exception as e:
                print(f"Erro ao ler pasta: {e}")
            return {"sucesso": True, "caminho": pasta, "temporadas": temporadas}
        return {"sucesso": False}

    def processar_fila(self, lista_musicas, pasta_anime_raiz):
        # Inicia numa Thread separada para não travar a janela do Windows!
        threading.Thread(target=self._executar_fila_thread, args=(lista_musicas, pasta_anime_raiz), daemon=True).start()

    def _executar_fila_thread(self, lista_musicas, pasta_anime_raiz):
        # 1. Limpa qualquer lixo residual da fila e liga o microfone dos logs!
        while not fila_logs.empty():
            fila_logs.get()
        sys.stdout.capturar = True 

        total = len(lista_musicas)
        print(f"\n[SISTEMA] Iniciando fila com {total} itens...\n")

        # 2. CONTAGEM INTELIGENTE DE "MAIN THEMES"
        qtd_main = sum(1 for m in lista_musicas if m['destino'] == 'Main Theme')
        tem_multi_main = qtd_main > 1

        temporadas_para_limpar = set()

        for i, musica in enumerate(lista_musicas):
            link = musica['link']
            nome = musica['nome']
            destino = musica['destino']
            lufs = musica['lufs']
            
            porcentagem = int((i / total) * 100)
            if i == 0:
                texto_perc = f"{porcentagem}%"
            else:
                texto_perc = f"{i}/{total} ({porcentagem}%)"

            janela.evaluate_js(f"window.atualizarStatusItem({i}, 'processando')")
            janela.evaluate_js(f"window.atualizarProgressoGlobal({porcentagem}, 'Downloading: {nome}...', '{texto_perc}')")

            try:
                arquivo_baixado = baixar_musica(link)
                
                janela.evaluate_js(f"window.atualizarProgressoGlobal({porcentagem}, 'Normalizing: {nome}...', '{texto_perc}')")
                if "Season" in destino:
                    tipo_tema = "temporada"
                    pasta_temp = destino
                    temporadas_para_limpar.add(pasta_temp)
                else:
                    tipo_tema = "main"
                    pasta_temp = None

                # 3. USA A VARIÁVEL INTELIGENTE AQUI AO INVÉS DO "TRUE" FIXO
                caminho_final = gerar_caminho_destino(pasta_anime_raiz, tipo_tema, nome, pasta_temp, multiplos_main=tem_multi_main)

                normalizar_e_salvar(arquivo_baixado, caminho_final, lufs)
                
                if os.path.exists(arquivo_baixado):
                    os.remove(arquivo_baixado)

                janela.evaluate_js(f"window.atualizarStatusItem({i}, 'concluido')")
                print(f"[SUCESSO] {nome} finalizado com sucesso!")
                
            except Exception as e:
                print(f"\n[ERRO] Falha ao processar {nome}: {str(e)}\n")
                janela.evaluate_js(f"window.atualizarStatusItem({i}, 'erro')")

        if temporadas_para_limpar:
            print("\n[SISTEMA] Iniciando Faxina Inteligente nas temporadas afetadas...")
            for temp in temporadas_para_limpar:
                mover_episodios_soltos(pasta_anime_raiz, temp)

        texto_final = f"{total}/{total} (100%)"
        janela.evaluate_js(f"window.atualizarProgressoGlobal(100, 'All operations completed!', '{texto_final}')")
        janela.evaluate_js("window.finalizarProcessamentoUI()")
        print("\n[SISTEMA] Fila concluída com sucesso! Aguardando novos comandos...")
        
        # 4. Desliga o log ao terminar para não pegar ruídos pós-processamento
        sys.stdout.capturar = False


    def testar_jellyfin(self, url, api_key):
        try:
            headers = {"Authorization": f'MediaBrowser Token="{api_key}"'}
            clean_url = url.rstrip('/')
            resposta = requests.get(f"{clean_url}/System/Info", headers=headers, timeout=5)
            if resposta.status_code == 200:
                return {"status": "sucesso", "mensagem": "✅ Connected Successfully!"}
            elif resposta.status_code == 401:
                return {"status": "erro", "mensagem": "❌ Invalid API Key"}
            return {"status": "erro", "mensagem": f"❌ Error code: {resposta.status_code}"}
        except:
            return {"status": "erro", "mensagem": "❌ Connection Failed"}
        
    def obter_configuracoes(self):
        return carregar_config()

    def salvar_configuracoes(self, dados):
        salvar_config(dados)
        return True

def iniciar_servidor():
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    # Redireciona saídas para capturarmos os logs na nossa rota
    sys.stdout = RedirecionadorLog(sys.__stdout__)
    sys.stderr = sys.stdout

    t = threading.Thread(target=iniciar_servidor)
    t.daemon = True
    t.start()

    api = Api()

    janela = webview.create_window(
        'Themarr - Sonarr/Plex Theme Manager', 
        'http://127.0.0.1:5000',
        width=780, 
        height=880,
        background_color='#1e1e1e',
        js_api=api
    )
    
    webview.start()
    sys.exit()