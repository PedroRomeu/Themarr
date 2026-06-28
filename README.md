# Themarr 🎵

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Stage: Development](https://img.shields.io/badge/Stage-In--Development-orange.svg)]()

**Themarr** is an automated theme music companion manager designed for media servers like **Jellyfin, Sonarr, and Plex**. It streamlines the process of downloading, normalizing, and injecting high-quality metadata into series and anime theme songs, ensuring a seamless and rich audio experience within your server ecosystem.

---

## ✨ Key Features

* **Smart Queue Processing:** Add multiple YouTube links, customize track names, and process them asynchronously without freezing the UI.
* **Audio Normalization:** Automatically normalizes audio tracks to broadcast standards (Target: `-24 LUFS` via FFmpeg `loudnorm`), avoiding jarring volume jumps between different show themes.
* **Intelligent Media Sorting:** Detects show structures and automatically places assets into their respective directories (e.g., season-specific paths or main root paths).
* **Jellyfin Integration (In Development):** Directly communicates with your Jellyfin server API to fetch official show metadata, genres, and posters.
* **Metadata Injection (ID3 Tags):** Automatically embeds album artwork, titles, albums (show names with year formatting removal), and genres into the final MP3 files.

---

## 🏗️ Architecture Blueprint

Themarr is evolving from a standalone desktop application into a lightweight, decoupled **Client-Server architecture**:
* **Backend:** Built with Python, leveraging `yt-dlp` for media extraction, `ffmpeg` for advanced audio DSP, and `mutagen` for metadata tag injection.
* **Frontend:** A scannable user interface designed to feel like a premium desktop application while maintaining the flexibility to be embedded as a Custom Tab directly inside media dashboards.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.10 or higher
* FFmpeg binaries configured in the `bin/` directory

### Installation

1. Clone the repository:
   ```bash
   git clone [https://github.com/YOUR-USERNAME/themarr.git](https://github.com/YOUR-USERNAME/themarr.git)
   cd themarr

2. Install the required dependencies:
    pip install -r requirements.txt

3. Run the application:
    python main.py

## 🗺️ Roadmap

[x] Multithreading architecture for responsive UI.

[x] Advanced FFmpeg audio normalization pipeline.

[x] Jellyfin API connection validation helper.

[ ] Automated ID3 Tag & Poster artwork injection.

[ ] Transition to a local lightweight Web-Server backend.

[ ] Jellyfin Custom Dashboard integration support.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

Developed with ❤️ by Pedro H.