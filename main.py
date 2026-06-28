import yt_dlp
import os
import subprocess
import shutil
import json
import threading
import sys
import queue
import requests # <-- NOVA BIBLIOTECA PARA A API
import customtkinter as ctk
from tkinter import filedialog

# --- NOVA ARQUITETURA DE LOGS ---
fila_logs = queue.Queue()

class RedirecionadorLog:
    def __init__(self, terminal_original):
        self.terminal = terminal_original

    def write(self, texto):
        if self.terminal:
            self.terminal.write(texto)
            self.terminal.flush()
        
        texto_limpo = texto.replace('\r', '\n')
        if texto_limpo:
            fila_logs.put(texto_limpo)

    def flush(self):
        if self.terminal:
            self.terminal.flush()

# --- CONFIGURAÇÕES E CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(BASE_DIR, 'bin', 'ffmpeg.exe')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# --- NOVO SISTEMA DE CONFIGURAÇÃO (AGORA SALVA TUDO) ---
def carregar_config():
    config_padrao = {
        "volume_lufs": -24,
        "jellyfin_url": "",
        "jellyfin_api": "",
        "use_jellyfin": False
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                dados = json.load(f)
                config_padrao.update(dados)
        except:
            pass
    return config_padrao

def salvar_config(novos_dados):
    dados_atuais = carregar_config()
    dados_atuais.update(novos_dados)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(dados_atuais, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar configuração: {e}")

# Variável global para carregar as configs na inicialização
app_config = carregar_config()

# ==========================================
# MOTOR DO PROGRAMA (DOWNLOAD E AUDIO)
# ==========================================
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

# ==========================================
# INTERFACE GRÁFICA (TELA PRINCIPAL)
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.geometry("750x850")
app.title("Themarr - Sonarr/Plex Theme Manager")

master_frame = ctk.CTkScrollableFrame(app, fg_color="transparent")
master_frame.pack(fill="both", expand=True)

# --- CABEÇALHO (NOVO) ---
frame_header = ctk.CTkFrame(master_frame, fg_color="transparent")
frame_header.pack(pady=(15, 10), padx=20, fill="x")

lbl_titulo_principal = ctk.CTkLabel(frame_header, text="Themarr Manager", font=("Segoe UI", 24, "bold"))
lbl_titulo_principal.pack(side="left")

# ==========================================
# JANELA DE SETTINGS E TESTE DE API (NOVO)
# ==========================================
def abrir_settings():
    janela_settings = ctk.CTkToplevel(app)
    janela_settings.title("Settings")
    janela_settings.geometry("500x400")
    janela_settings.transient(app) 
    janela_settings.grab_set() 
    
    # Carrega dados atualizados do config
    dados_atuais = carregar_config()

    lbl_jelly = ctk.CTkLabel(janela_settings, text="Jellyfin Integration", font=("Segoe UI", 18, "bold"))
    lbl_jelly.pack(pady=(20, 10))

    check_var = ctk.BooleanVar(value=dados_atuais.get("use_jellyfin", False))
    check_jellyfin = ctk.CTkCheckBox(janela_settings, text="Fetch Metadata from Jellyfin", variable=check_var)
    check_jellyfin.pack(pady=5)

    entrada_url = ctk.CTkEntry(janela_settings, width=350, placeholder_text="Jellyfin URL (e.g., http://192.168.1.100:8096)")
    entrada_url.insert(0, dados_atuais.get("jellyfin_url", ""))
    entrada_url.pack(pady=10)

    entrada_api = ctk.CTkEntry(janela_settings, width=350, placeholder_text="API Key")
    entrada_api.insert(0, dados_atuais.get("jellyfin_api", ""))
    entrada_api.pack(pady=10)

    lbl_status_api = ctk.CTkLabel(janela_settings, text="", font=("Segoe UI", 12))
    lbl_status_api.pack(pady=(5, 0))

    def testar_api():
        url = entrada_url.get().strip()
        api = entrada_api.get().strip()
        
        if not url or not api:
            lbl_status_api.configure(text="Please fill both URL and API Key!", text_color="red")
            return
            
        btn_testar.configure(state="disabled", text="Testing...")
        lbl_status_api.configure(text="Connecting...", text_color="white")

        def checar_conexao():
            try:
                # Prepara o cabeçalho de autorização padrão do Jellyfin
                headers = {"Authorization": f'MediaBrowser Token="{api}"'}
                clean_url = url.rstrip('/') # Tira a barra no final, se o usuário colocou
                
                # Bate na porta de informações do servidor
                resposta = requests.get(f"{clean_url}/System/Info", headers=headers, timeout=5)
                
                if resposta.status_code == 200:
                    lbl_status_api.configure(text="✅ Connected Successfully!", text_color="#00FF00")
                elif resposta.status_code == 401:
                    lbl_status_api.configure(text="❌ Invalid API Key (Unauthorized)", text_color="red")
                else:
                    lbl_status_api.configure(text=f"❌ Server returned error code: {resposta.status_code}", text_color="red")
            except Exception as e:
                lbl_status_api.configure(text="❌ Connection Failed (Server offline or wrong URL)", text_color="red")
            finally:
                btn_testar.configure(state="normal", text="🔄 Test Connection")

        # Roda o teste em segundo plano para não travar a janelinha
        threading.Thread(target=checar_conexao, daemon=True).start()

    btn_testar = ctk.CTkButton(janela_settings, text="🔄 Test Connection", fg_color="#444444", hover_color="#555555", command=testar_api)
    btn_testar.pack(pady=5)

    def salvar_e_fechar():
        novas_configs = {
            "use_jellyfin": check_var.get(),
            "jellyfin_url": entrada_url.get().strip(),
            "jellyfin_api": entrada_api.get().strip()
        }
        salvar_config(novas_configs)
        janela_settings.destroy()

    btn_salvar = ctk.CTkButton(janela_settings, text="💾 Save Configuration", fg_color="green", hover_color="darkgreen", command=salvar_e_fechar)
    btn_salvar.pack(side="bottom", pady=20)


# Botão que fica no cabeçalho
btn_settings = ctk.CTkButton(frame_header, text="⚙️ Settings", width=100, fg_color="#333333", hover_color="#444444", command=abrir_settings)
btn_settings.pack(side="right")


# ==========================================
# RESTANTE DA INTERFACE (SEM ALTERAÇÕES)
# ==========================================
volume_var = ctk.StringVar()

def validar_digitacao_volume(*args):
    texto = volume_var.get()
    if texto == "" or texto == "-": 
        return 
    try:
        valor = int(texto)
        if valor > 0:
            volume_var.set("0") 
            salvar_config({"volume_lufs": 0})
        else:
            salvar_config({"volume_lufs": valor})
    except ValueError:
        pass 

volume_var.trace_add("write", validar_digitacao_volume)

pasta_anime_selecionada = ""
temporadas_encontradas = []
fila_de_downloads = [] 
processando_agora = False 
log_visivel = False
editando_idx = -1 

spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
spinner_idx = 0

def animar_spinner():
    global spinner_idx
    if not processando_agora: return
    spinner_idx = (spinner_idx + 1) % len(spinner_frames)
    for tarefa in fila_de_downloads:
        if tarefa.get("status") == "processando" and "widget_btn" in tarefa:
            try:
                tarefa["widget_btn"].configure(text=spinner_frames[spinner_idx])
            except:
                pass
    app.after(100, animar_spinner)

def escolher_pasta_anime():
    global pasta_anime_selecionada, temporadas_encontradas
    pasta = filedialog.askdirectory(title="Select Anime Folder")
    if pasta:
        btn_iniciar.configure(text="▶ START PROCESSING", state="disabled", fg_color="gray", text_color_disabled="gray") 
        barra_progresso.set(0)
        lbl_progresso_texto.configure(text="0% (Ready)")
        caixa_log.delete("1.0", "end") 
        
        fila_de_downloads.clear()
        atualizar_interface_fila()
        
        pasta_anime_selecionada = pasta
        lbl_caminho_pasta.configure(text=f"Folder: {pasta}")
        temporadas_encontradas.clear()
        itens_na_pasta = os.listdir(pasta)
        for item in itens_na_pasta:
            if os.path.isdir(os.path.join(pasta, item)):
                if item != "theme-music":
                    temporadas_encontradas.append(item)
        opcoes_menu = ["Main"] 
        if len(temporadas_encontradas) == 0:
            nome_pasta_raiz = os.path.basename(pasta)
            temporada_perfeita = f"Season 01. {nome_pasta_raiz}"
            opcoes_menu.append(temporada_perfeita)
        else:
            opcoes_menu.extend(temporadas_encontradas)
            
        menu_destino.configure(values=opcoes_menu)
        menu_destino.set(opcoes_menu[0])
        btn_adicionar.configure(state="normal")

def set_editando_idx(idx):
    global editando_idx
    editando_idx = idx
    atualizar_interface_fila()

def salvar_edicao_nome(idx, novo_nome):
    global editando_idx
    if 0 <= idx < len(fila_de_downloads):
        if novo_nome.strip(): 
            fila_de_downloads[idx]['nome'] = novo_nome.strip()
    editando_idx = -1
    atualizar_interface_fila()

def mudar_destino_fila(idx, novo_destino):
    if 0 <= idx < len(fila_de_downloads):
        fila_de_downloads[idx]['destino'] = novo_destino

def atualizar_interface_fila():
    global editando_idx
    for widget in frame_lista_fila.winfo_children():
        widget.destroy()
        
    for i, tarefa in enumerate(fila_de_downloads):
        frame_item = ctk.CTkFrame(frame_lista_fila, fg_color="transparent")
        frame_item.pack(fill="x", pady=2, padx=5)
        
        status = tarefa.get("status", "pendente")
        pode_editar = (status == "pendente" or status == "erro")
        
        lbl_icone = ctk.CTkLabel(frame_item, text="🎵", font=("Segoe UI", 14))
        lbl_icone.pack(side="left", padx=(5, 0))
        
        if editando_idx == i and pode_editar:
            entrada_edit = ctk.CTkEntry(frame_item, width=200, height=25, font=("Segoe UI", 13))
            entrada_edit.insert(0, tarefa['nome'])
            entrada_edit.pack(side="left", padx=5)
            entrada_edit.focus()
            entrada_edit.select_range(0, 'end') 
            
            entrada_edit.bind("<Return>", lambda e, idx=i, ent=entrada_edit: salvar_edicao_nome(idx, ent.get()))
            entrada_edit.bind("<FocusOut>", lambda e, idx=i, ent=entrada_edit: salvar_edicao_nome(idx, ent.get()))
        else:
            lbl_nome = ctk.CTkLabel(frame_item, text=f"{tarefa['nome']}", font=("Segoe UI", 14))
            if pode_editar:
                lbl_nome.configure(cursor="hand2") 
                lbl_nome.bind("<Double-Button-1>", lambda e, idx=i: set_editando_idx(idx))
            lbl_nome.pack(side="left", padx=5)
            
        lbl_separador = ctk.CTkLabel(frame_item, text="|   🎯 Target:", font=("Segoe UI", 13), text_color="gray")
        lbl_separador.pack(side="left", padx=(5, 2))
        
        opcoes_destino = menu_destino.cget("values")
        menu_target = ctk.CTkOptionMenu(
            frame_item, values=opcoes_destino, width=120, height=25, font=("Segoe UI", 12),
            fg_color="#333333", button_color="#2b2b2b", button_hover_color="#3a3a3a", dropdown_fg_color="#2b2b2b",
            command=lambda val, idx=i: mudar_destino_fila(idx, val)
        )
        menu_target.set(tarefa['destino'])
        if not pode_editar:
            menu_target.configure(state="disabled") 
        menu_target.pack(side="left", padx=5)
        
        if status == "pendente":
            btn_status = ctk.CTkButton(frame_item, text="❌", width=30, height=30, 
                                       fg_color="transparent", hover_color="#8B0000", text_color="red",
                                       command=lambda idx=i: remover_da_fila(idx))
        elif status == "processando":
            btn_status = ctk.CTkLabel(frame_item, text="⠋", font=("Consolas", 18, "bold"), width=30, height=30, 
                                      fg_color="transparent", text_color="yellow")
        elif status == "concluido":
            btn_status = ctk.CTkLabel(frame_item, text="✓", font=("Segoe UI", 20, "bold"), width=30, height=30, 
                                      fg_color="transparent", text_color="#00FF00")
        elif status == "erro":
            btn_status = ctk.CTkLabel(frame_item, text="⚠️", font=("Segoe UI", 16), width=30, height=30, 
                                      fg_color="transparent", text_color="red")
            
        btn_status.pack(side="right", padx=5)
        tarefa["widget_btn"] = btn_status 
        
    if not processando_agora:
        if len(fila_de_downloads) > 0:
            btn_iniciar.configure(state="normal", fg_color="green", hover_color="darkgreen")
        else:
            if btn_iniciar.cget("text") != "✓ COMPLETED!":
                btn_iniciar.configure(state="disabled", fg_color="gray")

def remover_da_fila(index):
    if 0 <= index < len(fila_de_downloads):
        fila_de_downloads.pop(index)
        atualizar_interface_fila()

def adicionar_na_fila():
    link = entrada_link.get()
    nome = entrada_nome.get()
    destino = menu_destino.get()
    if not link or not nome:
        return
    tarefa = {"link": link, "nome": nome, "destino": destino, "status": "pendente"}
    fila_de_downloads.append(tarefa)
    atualizar_interface_fila()
    entrada_link.delete(0, 'end')
    entrada_nome.delete(0, 'end')

def alterar_volume(delta):
    try:
        atual = int(volume_var.get())
        novo = atual + delta
        if novo > 0: novo = 0
        if novo < -70: novo = -70
        volume_var.set(str(novo))
    except ValueError:
        pass

def iniciar_processamento_thread():
    btn_iniciar.configure(state="disabled", fg_color="gray", text="⏳ PROCESSING...")
    trabalhador = threading.Thread(target=processar_fila, daemon=True)
    trabalhador.start()

def processar_fila():
    global pasta_anime_selecionada, processando_agora
    processando_agora = True
    app.after(0, animar_spinner)
    
    total_tarefas = len(fila_de_downloads)
    try:
        volume_alvo = int(volume_var.get())
    except ValueError:
        volume_alvo = -24 

    total_mains = sum(1 for tarefa in fila_de_downloads if tarefa["destino"] == "Main")
    multiplos_main = (total_mains > 1) 

    for i, tarefa in enumerate(fila_de_downloads):
        tarefa["status"] = "processando"
        app.after(0, atualizar_interface_fila) 
        
        url = tarefa["link"]
        nome = tarefa["nome"]
        destino = tarefa["destino"]
        
        try:
            if destino != "Main":
                mover_episodios_soltos(pasta_anime_selecionada, destino)
                
            musica_bruta = baixar_musica(url)
            
            if destino == "Main":
                caminho_final = gerar_caminho_destino(pasta_anime_selecionada, "main", nome, multiplos_main=multiplos_main)
            else:
                caminho_final = gerar_caminho_destino(pasta_anime_selecionada, "temporada", nome, pasta_temporada=destino)
                
            normalizar_e_salvar(musica_bruta, caminho_final, volume_alvo)
            if os.path.exists(musica_bruta):
                os.remove(musica_bruta)
                
            tarefa["status"] = "concluido"
            
        except Exception as erro:
            print(f"\n=========================================")
            print(f"⚠️ ERRO CRÍTICO AO PROCESSAR '{nome}'!")
            print(f"Motivo: {str(erro)}")
            print(f"=========================================\n")
            tarefa["status"] = "erro"

        app.after(0, atualizar_interface_fila)
        
        progresso_atual = (i + 1) / total_tarefas
        app.after(0, lambda p=progresso_atual, idx=i: (
            barra_progresso.set(p),
            lbl_progresso_texto.configure(text=f"{int(p * 100)}% ({idx+1}/{total_tarefas})")
        ))
    
    processando_agora = False 
    app.after(0, finalizar_processamento)

def finalizar_processamento():
    btn_iniciar.configure(state="disabled", text="✓ COMPLETED!", fg_color="#28a745", text_color_disabled="white") 
    lbl_progresso_texto.configure(text="100% (Finished)")
    
    global pasta_anime_selecionada
    pasta_anime_selecionada = ""
    temporadas_encontradas.clear()
    lbl_caminho_pasta.configure(text="No folder selected")
    menu_destino.configure(values=["Select an anime folder first..."])
    menu_destino.set("Select an anime folder first...")
    btn_adicionar.configure(state="disabled")

def alternar_log():
    global log_visivel
    if log_visivel:
        frame_log.pack_forget() 
        frame_lista_fila.configure(height=130) 
        btn_toggle_log.configure(text="⬇ Show Detailed Logs")
        log_visivel = False
    else:
        frame_lista_fila.configure(height=50) 
        frame_log.pack(pady=(0, 15), padx=20, fill="both", expand=True) 
        btn_toggle_log.configure(text="⬆ Hide Logs")
        log_visivel = True

def atualizar_caixa_log():
    try:
        while not fila_logs.empty():
            texto = fila_logs.get_nowait()
            caixa_log.insert("end", texto)
            caixa_log.see("end")
    except queue.Empty:
        pass
    app.after(100, atualizar_caixa_log)


frame_alvo = ctk.CTkFrame(master_frame)
frame_alvo.pack(pady=10, padx=20, fill="x")

lbl_titulo = ctk.CTkLabel(frame_alvo, text="1. Select Anime Folder", font=("Segoe UI", 16, "bold"))
lbl_titulo.pack(pady=(10, 5))
btn_selecionar = ctk.CTkButton(frame_alvo, text="📂 Choose Folder", command=escolher_pasta_anime)
btn_selecionar.pack(pady=5)
lbl_caminho_pasta = ctk.CTkLabel(frame_alvo, text="No folder selected", text_color="gray")
lbl_caminho_pasta.pack(pady=(0, 10))

frame_form = ctk.CTkFrame(master_frame)
frame_form.pack(pady=10, padx=20, fill="x")

lbl_form = ctk.CTkLabel(frame_form, text="2. Add Music", font=("Segoe UI", 16, "bold"))
lbl_form.pack(pady=(10, 5))
entrada_link = ctk.CTkEntry(frame_form, placeholder_text="Paste YouTube link here...", width=400)
entrada_link.pack(pady=5)
entrada_nome = ctk.CTkEntry(frame_form, placeholder_text="Song name (e.g., Opening 1)", width=400)
entrada_nome.pack(pady=5)
menu_destino = ctk.CTkOptionMenu(frame_form, values=["Select an anime folder first..."], width=400)
menu_destino.pack(pady=5)

frame_volume_container = ctk.CTkFrame(frame_form, fg_color="transparent")
frame_volume_container.pack(pady=5)

lbl_vol = ctk.CTkLabel(frame_volume_container, text="Target Volume (LUFS):", font=("Segoe UI", 13))
lbl_vol.pack(side="left", padx=5)

btn_vol_menos = ctk.CTkButton(frame_volume_container, text="-", width=30, height=25, font=("Segoe UI", 14, "bold"), command=lambda: alterar_volume(-1))
btn_vol_menos.pack(side="left", padx=2)

volume_inicial = app_config.get("volume_lufs", -24)
volume_var.set(str(volume_inicial))
entrada_volume = ctk.CTkEntry(frame_volume_container, textvariable=volume_var, width=50, height=25, justify="center", font=("Segoe UI", 13, "bold"))
entrada_volume.pack(side="left", padx=2)

btn_vol_mais = ctk.CTkButton(frame_volume_container, text="+", width=30, height=25, font=("Segoe UI", 14, "bold"), command=lambda: alterar_volume(1))
btn_vol_mais.pack(side="left", padx=2)

btn_adicionar = ctk.CTkButton(frame_form, text="➕ Add to Queue", command=adicionar_na_fila, state="disabled")
btn_adicionar.pack(pady=(10, 15))

frame_fila_container = ctk.CTkFrame(master_frame)
frame_fila_container.pack(pady=10, padx=20, fill="both", expand=True)

lbl_fila = ctk.CTkLabel(frame_fila_container, text="3. Queue", font=("Segoe UI", 16, "bold"))
lbl_fila.pack(pady=(10, 5))
frame_lista_fila = ctk.CTkScrollableFrame(frame_fila_container, height=130)
frame_lista_fila.pack(padx=10, pady=5, fill="both", expand=True)

btn_iniciar = ctk.CTkButton(master_frame, text="▶ START PROCESSING", font=("Segoe UI", 14, "bold"), height=50, 
                            state="disabled", fg_color="gray", command=iniciar_processamento_thread)
btn_iniciar.pack(pady=(15, 5), padx=20, fill="x")

frame_progresso = ctk.CTkFrame(master_frame, fg_color="transparent")
frame_progresso.pack(pady=(5, 15), padx=20, fill="x")

lbl_progresso_texto = ctk.CTkLabel(frame_progresso, text="0% (Ready)", font=("Segoe UI", 14, "bold"))
lbl_progresso_texto.pack(pady=(0, 5))

barra_progresso = ctk.CTkProgressBar(frame_progresso, height=15)
barra_progresso.pack(fill="x")
barra_progresso.set(0.0)

btn_toggle_log = ctk.CTkButton(master_frame, text="⬇ Show Detailed Logs", fg_color="transparent", 
                               text_color="gray", hover_color="#2b2b2b", command=alternar_log)
btn_toggle_log.pack(pady=5)

frame_log = ctk.CTkFrame(master_frame)
caixa_log = ctk.CTkTextbox(frame_log, height=150, font=("Consolas", 12), fg_color="black", text_color="#00FF00")
caixa_log.pack(fill="both", expand=True, padx=2, pady=2)

sys.stdout = RedirecionadorLog(sys.__stdout__)
sys.stderr = sys.stdout 

atualizar_caixa_log() 

if __name__ == "__main__":
    app.mainloop()