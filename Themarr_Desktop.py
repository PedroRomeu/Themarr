import webview
from main import iniciar_flask_background, api_sistema

if __name__ == '__main__':
    iniciar_flask_background()
    
    janela = webview.create_window(
        "Themarr Manager", 
        "http://127.0.0.1:5000", 
        js_api=api_sistema, 
        width=900, 
        height=750, 
        background_color='#1e1e1e'
    )
    
    webview.start()