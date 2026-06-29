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
import re
import tempfile
import subprocess
import shutil
import socket
import tkinter as tk
from tkinter import filedialog

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Manda o Flask silenciar as mensagens de "GET /api/logs"

# Inicia o servidor Flask (Backend)
app = Flask(__name__)

# --- 1. REINTEGRANDO SEU MOTOR DE LOGS ANTIGO ---
fila_logs = queue.Queue()

class RedirecionadorLog:
    def __init__(self, terminal_original):
        self.terminal = terminal_original
        self.capturar = True # <-- AGORA FICA LIGADO DESDE O INÍCIO!

    def write(self, texto):
        if self.terminal:
            self.terminal.write(texto)
            self.terminal.flush()
        
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

# NOVA LÓGICA: Salva o config na pasta de perfil do usuário logado no Windows
USER_HOME = os.path.expanduser('~')
PASTA_CONFIG = os.path.join(USER_HOME, '.themarr_manager')
os.makedirs(PASTA_CONFIG, exist_ok=True) # Cria a pasta automaticamente se ela não existir

CONFIG_FILE = os.path.join(PASTA_CONFIG, 'config.json')

def normalizar_audio_ffmpeg(caminho_mp3, lufs_alvo):
    """
    Roda o FFmpeg para normalizar o áudio, imitando a lógica segura do seu arquivo .bat antigo.
    """
    arquivo_temp = caminho_mp3 + ".temp.mp3"
    
    # A CORREÇÃO FOI AQUI: Substituímos "ffmpeg" por FFMPEG_PATH
    comando = [
        FFMPEG_PATH, "-hide_banner", "-loglevel", "error", "-y",
        "-i", caminho_mp3,
        "-filter:a", f"loudnorm=I={lufs_alvo}:LRA=11:TP=-1.0",
        "-b:a", "320k",
        arquivo_temp
    ]
    
    try:
        # Executa sem abrir janelas pretas (startupinfo protege isso no Windows)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        subprocess.run(comando, check=True, startupinfo=startupinfo)
        
        # Verifica se deu certo e se o arquivo não está vazio (como no seu .bat)
        if os.path.exists(arquivo_temp) and os.path.getsize(arquivo_temp) > 0:
            shutil.move(arquivo_temp, caminho_mp3) # Substitui silenciosamente
            return True
        else:
            if os.path.exists(arquivo_temp):
                os.remove(arquivo_temp)
            return False
    except Exception as e:
        print(f"[FFMPEG] ❌ Erro ao normalizar {caminho_mp3}: {e}")
        if os.path.exists(arquivo_temp):
            os.remove(arquivo_temp)
        return False

# ==========================================
# FUNÇÕES DE MEMÓRIA (CONFIGURAÇÕES)
# ==========================================
def carregar_config():
    padrao = {
        "lufs": "-24", 
        "jelly_check": False, 
        "jelly_url": "", 
        "jelly_api": "",
        "open_browser": True
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                # Atualiza os padrões com o que existir no arquivo
                for chave in dados:
                    if chave in padrao: # Agora o open_browser vai passar nesse teste!
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

def processar_capas_pasta_atual(caminho_pasta_anime, nome_pasta_anime, config):
    print(f"\n[AUTOMAÇÃO] 🎬 Iniciando processamento de metadados para: {nome_pasta_anime}")
    
    nomes_capas_locais = ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "poster.jpg", "poster.png"]
    caminho_imagem_final = None
    imagem_temporaria = False 
    
    # Valores padrão caso o Jellyfin esteja desligado
    genero_final = "" 
    nome_album_final = nome_pasta_anime 

    # PRIORIDADE 2 - Imagem local
    for nome_arquivo in nomes_capas_locais:
        caminho_teste = os.path.join(caminho_pasta_anime, nome_arquivo)
        if os.path.exists(caminho_teste):
            print(f"[AUTOMAÇÃO] 🔍 Prioridade 2 Ativada: Imagem local encontrada ({nome_arquivo})")
            caminho_imagem_final = caminho_teste
            break

    # BUSCA DE DADOS NO JELLYFIN (Para Gênero, Nome Limpo e Capa se faltar)
    url_jelly = config.get("jelly_url")
    api_jelly = config.get("jelly_api")
    
    if url_jelly and api_jelly:
        print("[AUTOMAÇÃO] 🌐 Consultando Jellyfin para metadados adicionais...")
        resultado_busca = buscar_dados_jellyfin(nome_pasta_anime, url_jelly, api_jelly)
        
        if resultado_busca["sucesso"]:
            # MÁGICA 1: Pega o gênero real que o Jellyfin retornou!
            genero_final = resultado_busca["generos"]
            
            # MÁGICA 2: Usa o nome OFICIAL do anime sem o ano para o álbum (ex: "86: Eighty-Six")
            nome_album_final = resultado_busca["nome_oficial"]
            
            if genero_final:
                print(f"[AUTOMAÇÃO] 🏷️ Gêneros encontrados: {genero_final}")
            
            # PRIORIDADE 1 - Baixa a capa só se não achou localmente
            if not caminho_imagem_final and resultado_busca["url_imagem"]:
                pasta_temp = tempfile.gettempdir()
                nome_arquivo_temp = f"temp_cover_{resultado_busca['serie_id']}.jpg"
                
                caminho_imagem_final = baixar_imagem_jellyfin(
                    url_imagem=resultado_busca["url_imagem"],
                    api_key=api_jelly,
                    pasta_destino=pasta_temp,
                    nome_arquivo=nome_arquivo_temp
                )
                imagem_temporaria = True
    else:
        print("[AUTOMAÇÃO] ⚠️ Jellyfin não configurado/desmarcado. Pulando busca online.")

    # APLICAR METADADOS NOS MP3
    print("[AUTOMAÇÃO] 🚀 Varrendo a pasta para aplicar metadados nos arquivos MP3...")
    mp3_encontrados = 0
    
    for raiz, subpastas, arquivos in os.walk(caminho_pasta_anime):
        for arquivo in arquivos:
            if arquivo.lower().endswith('.mp3'):
                caminho_completo_mp3 = os.path.join(raiz, arquivo)
                titulo_musica = os.path.splitext(arquivo)[0]
                
                # Injeta os dados limpos!
                if injetar_metadados_mp3(caminho_completo_mp3, caminho_imagem_final, titulo_musica, nome_album_final, genero_final):
                    mp3_encontrados += 1
                    
    print(f"[AUTOMAÇÃO] ✨ Concluído! Metadados aplicados em {mp3_encontrados} arquivo(s) MP3.")
    
    # FAXINA TEMPORÁRIA
    if imagem_temporaria and caminho_imagem_final:
        try:
            os.remove(caminho_imagem_final)
            print("[AUTOMAÇÃO] 🧹 Arquivo de imagem temporário apagado com sucesso. Pasta limpa!")
        except Exception as e:
            print(f"[AUTOMAÇÃO] ⚠️ Não foi possível apagar a imagem temporária: {e}")

def limpar_nome_pesquisa(nome_pasta, remover_ano=False):
    # Troca caracteres problemáticos (como o dois pontos japonês e traços) por espaços
    nome_limpo = nome_pasta.replace('：', ' ').replace('-', ' ')
    
    if remover_ano:
        # Modo Sobrevivência: Arranca tudo dentro de (), [] e {}
        nome_limpo = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', nome_limpo)
    else:
        # Modo Preciso: Arranca apenas [] e {}, MANTENDO o (Ano)
        nome_limpo = re.sub(r'\[.*?\]|\{.*?\}', '', nome_limpo)
    
    # Remove espaços duplos
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo)
    return nome_limpo.strip()

def buscar_dados_jellyfin(nome_pasta, url_jellyfin, api_key):
    clean_url = url_jellyfin.rstrip('/')
    headers = {"X-Emby-Token": api_key} 

    def tentar_buscar(termo):
        params = {
            "searchTerm": termo,
            "IncludeItemTypes": "Series",
            "Recursive": "true",
            "Fields": "Genres"
        }
        try:
            res = requests.get(f"{clean_url}/Items", headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                dados = res.json()
                if dados.get("Items") and len(dados["Items"]) > 0:
                    serie = dados["Items"][0]
                    
                    # ==================================================
                    # A MUDANÇA FOI FEITA AQUI:
                    # Capturamos a lista de gêneros e juntamos com vírgula
                    # ==================================================
                    generos_lista = serie.get("Genres", [])
                    generos_string = ", ".join(generos_lista) if generos_lista else ""

                    return {
                        "sucesso": True, 
                        "nome_oficial": serie.get("Name"), 
                        "serie_id": serie.get("Id"),
                        "url_imagem": f"{clean_url}/Items/{serie.get('Id')}/Images/Primary",
                        "generos": generos_string  # <-- E enviamos ele aqui pro resto do programa!
                    }
        except Exception as e:
            pass
        return {"sucesso": False}

    # ==========================================
    # ETAPA 1: Busca Precisa (Mantendo o Ano)
    # ==========================================
    termo_preciso = limpar_nome_pesquisa(nome_pasta, remover_ano=False)
    print(f"\n[JELLYFIN] Pesquisando (Modo Preciso): '{termo_preciso}'...")
    resultado = tentar_buscar(termo_preciso)
    if resultado["sucesso"]:
        print(f"[JELLYFIN] ✅ Encontrado: {resultado['nome_oficial']}")
        return resultado

    # ==========================================
    # ETAPA 2: Busca Genérica (Removendo o Ano)
    # ==========================================
    termo_generico = limpar_nome_pesquisa(nome_pasta, remover_ano=True)
    if termo_generico != termo_preciso:
        print(f"[JELLYFIN] ⚠️ Não encontrado. Tentando Busca Genérica: '{termo_generico}'...")
        resultado = tentar_buscar(termo_generico)
        if resultado["sucesso"]:
            print(f"[JELLYFIN] ✅ Encontrado via Fallback: {resultado['nome_oficial']}")
            return resultado

    # ==========================================
    # ETAPA 3: Busca Ampla (Primeiras 2 Palavras)
    # ==========================================
    palavras = termo_generico.split()
    if len(palavras) > 1:
        termo_amplo = " ".join(palavras[:2])
        print(f"[JELLYFIN] ⚠️ Não encontrado. Tentando Busca Ampla: '{termo_amplo}'...")
        resultado = tentar_buscar(termo_amplo)
        if resultado["sucesso"]:
            print(f"[JELLYFIN] ✅ Encontrado via Busca Ampla: {resultado['nome_oficial']}")
            return resultado

    # ==========================================
    # ETAPA 4: Busca Ultra Ampla (Apenas 1ª Palavra)
    # ==========================================
    if len(palavras) > 0:
        termo_ultra_amplo = palavras[0]
        print(f"[JELLYFIN] ⚠️ Não encontrado. Tentando Busca Ultra Ampla: '{termo_ultra_amplo}'...")
        resultado = tentar_buscar(termo_ultra_amplo)
        if resultado["sucesso"]:
            print(f"[JELLYFIN] ✅ Encontrado via Busca Ultra Ampla: {resultado['nome_oficial']}")
            return resultado

    print(f"[JELLYFIN] ❌ Nenhuma série encontrada para a pasta '{nome_pasta}'.")
    return {"sucesso": False}

def baixar_imagem_jellyfin(url_imagem, api_key, pasta_destino, nome_arquivo="cover.jpg"):
    """
    Faz o download da imagem de capa do Jellyfin e salva na pasta de destino.
    """
    headers = {"X-Emby-Token": api_key}
    caminho_completo = os.path.join(pasta_destino, nome_arquivo)
    
    try:
        print(f"[JELLYFIN] 📥 Iniciando download da imagem de capa...")
        # stream=True faz o download em partes, consumindo menos memória
        res = requests.get(url_imagem, headers=headers, stream=True, timeout=15)
        
        if res.status_code == 200:
            # Garante que a pasta existe antes de salvar
            os.makedirs(pasta_destino, exist_ok=True)
            
            # Salva o arquivo em modo binário ('wb')
            with open(caminho_completo, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"[JELLYFIN] 💾 Imagem salva com sucesso em: {caminho_completo}")
            return caminho_completo
        else:
            print(f"[JELLYFIN] ❌ Falha ao baixar imagem. Servidor retornou Status: {res.status_code}")
            return None
            
    except Exception as e:
        print(f"[JELLYFIN] ❌ Erro durante o download da imagem: {e}")
        return None
    
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error, TIT2, TPE1, TALB, TPE2, TCON

def injetar_metadados_mp3(caminho_mp3, caminho_imagem, titulo, album, genero):
    """
    Injeta a imagem de capa e metadados essenciais e limpos no arquivo .mp3.
    """
    try:
        audio = MP3(caminho_mp3, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass 
            
        # 1. INJETANDO OS TEXTOS LIMPOS
        audio.tags.add(TIT2(encoding=3, text=titulo))  # Título (Nome do arquivo)
        
        # Álbum (Nome limpo do anime). Se você preferir 100% vazio, basta comentar a linha abaixo:
        audio.tags.add(TALB(encoding=3, text=album))   
        
        # Gênero dinâmico do Jellyfin
        if genero:
            audio.tags.add(TCON(encoding=3, text=genero))          
        
        # 2. INJETANDO A IMAGEM
        if caminho_imagem and os.path.exists(caminho_imagem):
            with open(caminho_imagem, 'rb') as f:
                dados_imagem = f.read()
                
            mime_type = 'image/png' if caminho_imagem.lower().endswith('.png') else 'image/jpeg'
            
            audio.tags.add(
                APIC(
                    encoding=3,       
                    mime=mime_type,   
                    type=3,           
                    desc=u'Cover',    
                    data=dados_imagem 
                )
            )
        
        audio.save(v2_version=3)
        return True
        
    except Exception as e:
        print(f"[MP3] ❌ Erro ao injetar metadados: {e}")
        return False

# =======================================================
# PONTE DE COMUNICAÇÃO JS -> PYTHON (A CLASSE API)
# =======================================================
class Api:
    def selecionar_pasta(self):
        try:
            pasta = ""
            # 1. Tenta abrir pelo PyWebView (Modo Desktop)
            if len(webview.windows) > 0:
                resultado = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                if resultado:
                    pasta = resultado[0]
            else:
                # 2. Fallback (Modo Server): Usa o Tkinter nativo para forçar a janela do Windows!
                root = tk.Tk()
                root.withdraw() # Esconde a janela principal cinza do Tkinter
                root.attributes('-topmost', True) # Força a janela a pular por cima do Navegador
                pasta = filedialog.askdirectory(title="Selecione o diretório de Mídia")
                root.destroy()
            
            # Se o usuário fechou a janela sem selecionar nada
            if not pasta:
                return {"sucesso": False, "erro": "Nenhuma pasta selecionada."}
                
            # Varre as temporadas
            temporadas = []
            try:
                for item in os.listdir(pasta):
                    if os.path.isdir(os.path.join(pasta, item)) and item != "theme-music":
                        temporadas.append(item)
            except Exception as e:
                print(f"Erro ao ler pasta: {e}")
                
            return {"sucesso": True, "caminho": pasta, "temporadas": temporadas}
            
        except Exception as e:
            print(f"Erro fatal no Browse: {e}")
            return {"sucesso": False, "erro": str(e)}

    def melhorar_musicas_locais(self, pasta_alvo, modo_batch, lufs_alvo):
        if not pasta_alvo or not os.path.exists(pasta_alvo):
            return {"status": "erro", "mensagem": "Invalid directory."}
            
        try:
            print("\n=======================================================")
            print("[ENHANCE] Iniciando processo de melhoria de áudio...")
            print(f"[ENHANCE] Modo Batch (Todas as subpastas): {'Sim' if modo_batch else 'Não'}")
            print(f"[ENHANCE] Volume Alvo: {lufs_alvo} LUFS")
            print("=======================================================\n")

            arquivos_afetados = 0
            pastas_para_processar = []
            
            if modo_batch:
                for item in os.listdir(pasta_alvo):
                    caminho_item = os.path.join(pasta_alvo, item)
                    if os.path.isdir(caminho_item):
                        pastas_para_processar.append(caminho_item)
            else:
                pastas_para_processar.append(pasta_alvo)

            config_atual = self.obter_configuracoes() 
            
            for pasta_anime in pastas_para_processar:
                nome_anime = os.path.basename(pasta_anime)
                mp3s_nesta_pasta = []
                
                for raiz, _, arquivos in os.walk(pasta_anime):
                    for arquivo in arquivos:
                        if arquivo.lower().endswith('.mp3'):
                            caminho_mp3 = os.path.join(raiz, arquivo)
                            mp3s_nesta_pasta.append(caminho_mp3)
                
                if not mp3s_nesta_pasta:
                    continue 
                
                print(f"\n[ENHANCE] ✨ Melhorando áudios na pasta: {nome_anime}")
                
                for mp3 in mp3s_nesta_pasta:
                    print(f"[ENHANCE] 🎚️ Normalizando: {os.path.basename(mp3)}")
                    if normalizar_audio_ffmpeg(mp3, lufs_alvo):
                        arquivos_afetados += 1
                        
                processar_capas_pasta_atual(pasta_anime, nome_anime, config_atual)
                
            print("\n=======================================================")
            print(f"[ENHANCE] Concluído! {arquivos_afetados} arquivo(s) modificado(s).")
            print("=======================================================\n")
            
            if arquivos_afetados > 0:
                return {"status": "sucesso", "mensagem": f"Done! {arquivos_afetados} files enhanced."}
            else:
                return {"status": "sucesso", "mensagem": "No .mp3 files found to enhance."}
                
        except Exception as e:
            print(f"\n[ENHANCE] ❌ Erro crítico: {e}")
            return {"status": "erro", "mensagem": f"Error: {str(e)}"}

    def apagar_musicas_pasta(self, pasta_raiz):
        if not pasta_raiz or not os.path.exists(pasta_raiz):
            return {"status": "erro", "mensagem": "Invalid or missing directory."}
        
        apagados = 0
        try:
            print(f"\n=======================================================")
            print(f"[CLEANUP] Iniciando limpeza de áudios em: {pasta_raiz}")
            print(f"=======================================================\n")
            
            for raiz, subpastas, arquivos in os.walk(pasta_raiz):
                for arquivo in arquivos:
                    if arquivo.lower().endswith('.mp3'):
                        caminho_completo = os.path.join(raiz, arquivo)
                        os.remove(caminho_completo)
                        print(f"[CLEANUP] 🗑️ Removido: {arquivo}")
                        apagados += 1
            
            for raiz, subpastas, arquivos in os.walk(pasta_raiz, topdown=False):
                for subpasta in subpastas:
                    if subpasta.lower() == 'theme-music':
                        caminho_sub = os.path.join(raiz, subpasta)
                        if not os.listdir(caminho_sub): 
                            os.rmdir(caminho_sub)
                            print(f"[CLEANUP] 📁 Pasta vazia removida: {caminho_sub}")
                            
            print(f"\n[CLEANUP] Concluído! {apagados} arquivo(s) removido(s).")
            return {"status": "sucesso", "mensagem": f"Cleaned up! {apagados} audio file(s) removed."}
            
        except Exception as e:
            print(f"[CLEANUP] ❌ Erro: {e}")
            return {"status": "erro", "mensagem": f"Error during cleanup: {str(e)}"}

    def obter_status(self):
        global estado_global
        logs = ""
        while not fila_logs.empty():
            logs += fila_logs.get()
            
        return {
            "logs": logs,
            "is_processing": estado_global["is_processing"],
            "porcentagem": estado_global["porcentagem"],
            "textoStatus": estado_global["textoStatus"],
            "textoPorcentagem": estado_global["textoPorcentagem"],
            "itens_status": estado_global["itens_status"]
        }

    def processar_fila(self, lista_musicas, pasta_anime_raiz):
        global estado_global
        estado_global["is_processing"] = True
        estado_global["porcentagem"] = 0
        estado_global["textoStatus"] = "Starting..."
        estado_global["textoPorcentagem"] = "0%"
        estado_global["itens_status"] = ["aguardando"] * len(lista_musicas)

        t = threading.Thread(target=self._executar_fila_thread, args=(lista_musicas, pasta_anime_raiz))
        t.daemon = True
        t.start()
        return True

    def _executar_fila_thread(self, lista_musicas, pasta_anime_raiz):
        global estado_global

        total = len(lista_musicas)
        print(f"\n[SISTEMA] Iniciando fila com {total} itens...\n")

        qtd_main = sum(1 for m in lista_musicas if m['destino'] == 'Main Theme')
        tem_multi_main = qtd_main > 1
        temporadas_para_limpar = set()

        for i, musica in enumerate(lista_musicas):
            link = musica['link']
            nome = musica['nome']
            destino = musica['destino']
            lufs = musica['lufs']
            
            porcentagem = int((i / total) * 100)
            texto_perc = f"{porcentagem}%" if i == 0 else f"{i}/{total} ({porcentagem}%)"

            # Atualiza o quadro de avisos global
            estado_global["itens_status"][i] = "processando"
            estado_global["porcentagem"] = porcentagem
            estado_global["textoStatus"] = f"Downloading: {nome}..."
            estado_global["textoPorcentagem"] = texto_perc

            try:
                arquivo_baixado = baixar_musica(link)
                
                estado_global["textoStatus"] = f"Normalizing: {nome}..."
                
                if "Season" in destino:
                    tipo_tema = "temporada"
                    pasta_temp = destino
                    temporadas_para_limpar.add(pasta_temp)
                else:
                    tipo_tema = "main"
                    pasta_temp = None

                caminho_final = gerar_caminho_destino(pasta_anime_raiz, tipo_tema, nome, pasta_temp, multiplos_main=tem_multi_main)
                normalizar_e_salvar(arquivo_baixado, caminho_final, lufs)
                
                if os.path.exists(arquivo_baixado):
                    os.remove(arquivo_baixado)

                estado_global["itens_status"][i] = "concluido"
                print(f"[SUCESSO] {nome} finalizado com sucesso!")
                
            except Exception as e:
                print(f"\n[ERRO] Falha ao processar {nome}: {str(e)}\n")
                estado_global["itens_status"][i] = "erro"

        if temporadas_para_limpar:
            print("\n[SISTEMA] Iniciando Faxina Inteligente nas temporadas afetadas...")
            for temp in temporadas_para_limpar:
                mover_episodios_soltos(pasta_anime_raiz, temp)

        estado_global["porcentagem"] = 99
        estado_global["textoStatus"] = "Applying Cover Arts..."
        estado_global["textoPorcentagem"] = "99%"
        
        config_atual = carregar_config()
        nome_do_anime = os.path.basename(pasta_anime_raiz)
        
        if not config_atual.get("jelly_check"):
            config_atual["jelly_url"] = ""
            config_atual["jelly_api"] = ""

        processar_capas_pasta_atual(pasta_anime_raiz, nome_do_anime, config_atual)

        # Processo terminado!
        estado_global["porcentagem"] = 100
        estado_global["textoStatus"] = "All operations completed!"
        estado_global["textoPorcentagem"] = f"{total}/{total} (100%)"
        estado_global["is_processing"] = False # Desliga a flag de processamento!
        
        print("\n[SISTEMA] Fila concluída com sucesso! Aguardando novos comandos...")


    def testar_jellyfin(self, url, api_key):
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            url = str(url).strip().strip('"').strip("'")
            api_key = str(api_key).strip().strip('"').strip("'")
            
            if not url.startswith('http'):
                url = 'http://' + url
            clean_url = url.rstrip('/')
            
            headers = {
                "X-Emby-Token": api_key,
                "Accept": "application/json"
            }
            
            resposta = requests.get(f"{clean_url}/System/Info", headers=headers, timeout=5, verify=False)
            
            if resposta.status_code == 200:
                return {"status": "sucesso", "mensagem": "✅ Connected Successfully!"}
            else:
                return {"status": "erro", "mensagem": f"❌ Error {resposta.status_code}: API Key rejected by server."}
                
        except Exception as e:
            return {"status": "erro", "mensagem": f"❌ Connection Error: {str(e)}"}
        
    def obter_configuracoes(self):
        return carregar_config()

    def salvar_configuracoes(self, dados):
        salvar_config(dados)
        return True

# ========================================================
# ESTADO GLOBAL DO SISTEMA (Novo Padrão Polling)
# ========================================================
estado_global = {
    "is_processing": False,
    "porcentagem": 0,
    "textoStatus": "Ready",
    "textoPorcentagem": "0%",
    "itens_status": []  # Guarda se o item está em 'aguardando', 'processando', 'concluido' ou 'erro'
}

# ========================================================
# ROTAS DO FLASK PARA O MODO NAVEGADOR (O "PLANO B")
# ========================================================
# Criamos a API aqui fora para o Flask e a Janela usarem a mesma!
api_sistema = Api() 

@app.route('/api/selecionar_pasta', methods=['POST'])
def flask_selecionar_pasta():
    # Chama a função da API e retorna como JSON pro navegador
    resultado = api_sistema.selecionar_pasta()
    return jsonify(resultado)

@app.route('/api/obter_configuracoes', methods=['GET'])
def flask_obter_configuracoes():
    return jsonify(api_sistema.obter_configuracoes())

@app.route('/api/salvar_configuracoes', methods=['POST'])
def flask_salvar_configuracoes():
    dados = request.json
    api_sistema.salvar_configuracoes(dados)
    return jsonify({"status": "sucesso"})

@app.route('/api/processar_fila', methods=['POST'])
def api_flask_processar_fila():
    dados = request.json
    fila = dados.get('fila', [])
    pasta = dados.get('pasta', '')
    api_sistema.processar_fila(fila, pasta)
    return jsonify({"status": "sucesso"})

@app.route('/api/status', methods=['GET'])
def api_flask_status():
    return jsonify(api_sistema.obter_status())

@app.route('/api/testar_jellyfin', methods=['POST'])
def api_flask_testar_jellyfin():
    try:
        dados = request.get_json(force=True, silent=True) or {}
        
        url = dados.get('url', '')
        # Agora o Flask é inteligente: procura por 'api_key', e se não achar, procura por 'api'
        api_key = dados.get('api_key', dados.get('api', '')) 
        
        print(f"\n[RECEIVED FROM BROWSER] URL: {url} | API: {api_key}")
        
        resultado = api_sistema.testar_jellyfin(url, api_key)
        return jsonify(resultado)
        
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"❌ Flask Route Error: {str(e)}"})
    
@app.route('/api/apagar_musicas_pasta', methods=['POST'])
def api_flask_apagar_musicas():
    try:
        dados = request.get_json(force=True, silent=True) or {}
        pasta = dados.get('pasta', '')
        
        print(f"\n[RECEIVED FROM BROWSER] Delete files in: {pasta}")
        
        resultado = api_sistema.apagar_musicas_pasta(pasta)
        return jsonify(resultado)
        
    except Exception as e:
        print(f"[FLASK ERROR] Delete failed: {e}")
        return jsonify({"status": "erro", "mensagem": f"❌ Server Error: {str(e)}"})


@app.route('/api/melhorar_musicas_locais', methods=['POST'])
def api_flask_melhorar_musicas():
    try:
        dados = request.get_json(force=True, silent=True) or {}
        
        # Puxando exatamente os nomes que o Javascript envia
        pasta = dados.get('pasta', '')
        modo_batch = dados.get('modoBatch', False)
        lufs = dados.get('lufs', '-24')
        
        print(f"\n[RECEIVED FROM BROWSER] Enhance - Folder: {pasta} | Batch: {modo_batch} | LUFS: {lufs}")
        
        resultado = api_sistema.melhorar_musicas_locais(pasta, modo_batch, lufs)
        return jsonify(resultado)
        
    except Exception as e:
        print(f"[FLASK ERROR] Enhance failed: {e}")
        return jsonify({"status": "erro", "mensagem": f"❌ Server Error: {str(e)}"})

# ========================================================

def iniciar_servidor():
    app.run(host='127.0.0.1', port=5000, debug=False)

def aplicativo_ja_esta_rodando():
    """Tenta conectar na porta 5000. Se conseguir, é porque já tem uma instância do Themarr aberta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # connect_ex retorna 0 se a conexão for bem sucedida (porta ocupada)
        return s.connect_ex(('127.0.0.1', 5000)) == 0

def iniciar_flask_background():
    #CHECAGEM DE INSTÂNCIA DUPLA
    if aplicativo_ja_esta_rodando():
        print("Uma instância do Themarr já está rodando. Fechando esta nova tentativa...")
        sys.exit(0)

    # Redireciona saídas para capturarmos os logs na nossa rota web
    sys.stdout = RedirecionadorLog(sys.__stdout__)
    sys.stderr = sys.stdout
    
    t = threading.Thread(target=iniciar_servidor)
    t.daemon = True
    t.start()

if __name__ == '__main__':
    
    iniciar_flask_background()
    
    # Abre a janela clássica do PyWebView
    janela = webview.create_window(
        "Themarr Manager", 
        "http://127.0.0.1:5000", 
        js_api=api_sistema,
        width=900, 
        height=750, 
        background_color='#1e1e1e'
    )
    
    webview.start()
    sys.exit()