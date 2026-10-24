import webview
from main import start_flask_background, api_system

if __name__ == '__main__':
    start_flask_background()

    window = webview.create_window(
        "Themarr",
        "http://127.0.0.1:5000",
        js_api=api_system,
        width=1200,
        height=800,
        min_size=(760, 560),
        background_color='#141418'
    )

    webview.start()
