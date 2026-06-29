import os
import webbrowser
import pystray
from PIL import Image, ImageDraw
from main import iniciar_flask_background, carregar_config

def create_tray_icon():
    image = Image.new('RGB', (64, 64), color=(30, 30, 30))
    d = ImageDraw.Draw(image)
    d.text((15, 25), "TM", fill=(59, 130, 246)) 
    return image

def on_open_browser(icon, item):
    webbrowser.open("http://127.0.0.1:5000")

def on_exit(icon, item):
    icon.stop()
    os._exit(0)

if __name__ == '__main__':
    iniciar_flask_background()
    
    config = carregar_config()
    if config.get("open_browser", True):
        webbrowser.open("http://127.0.0.1:5000")
        
    icon = pystray.Icon("Themarr")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Open in Browser", on_open_browser),
        pystray.MenuItem("Exit", on_exit)
    )
    icon.icon = create_tray_icon()
    icon.title = "Themarr Server"
    icon.run()