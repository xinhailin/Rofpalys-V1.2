<div align="center">

<!-- Rotating Cube Animation (GitHub Safe) -->
<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Musical%20Notes.png" alt="Rofpalys Logo" width="100" />
<br><br>

<!-- Aesthetic Loading Cube -->
<div align="center">
  <img src="https://user-images.githubusercontent.com/74038190/212284100-561aa473-3905-4a80-b561-0d28506553ee.gif" width="150" alt="Rotating Cube">
</div>

# 🎵 Rofpalys V1.2
**The Ultimate AI-Powered, Modular Music Player for Termux.**

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Termux](https://img.shields.io/badge/Termux-Android-black.svg?style=for-the-badge&logo=android&logoColor=green)](https://termux.dev)
[![License](https://img.shields.io/badge/License-Private-red.svg?style=for-the-badge)]()
[![Architecture](https://img.shields.io/badge/Architecture-Modular-purple.svg?style=for-the-badge)]()

*Built with 40+ modules, engineered for low-end devices (4GB RAM), and powered by the CyroKayAI engine.*

</div>

---

## 📖 About Rofpalys

Rofpalys is not just a music player; it's a complete **Media Suite** built entirely inside Termux. Designed to push the limits of mobile Linux, it features a custom GUI, multi-engine audio support, real-time visualizers, and an advanced local AI that synchronizes lyrics like Spotify.

### ✨ Key Features
- 🧠 **CyroKayAI Engine**: Local AI that analyzes audio waves, detects vocals (FFT), and perfectly syncs lyrics (Viterbi algorithm). No cloud needed.
- 🎨 **Aesthetic UI & Themes**: 3 built-in themes (Classic, Modern, Cyberpunk) with smooth scrolling lyrics.
- 📊 **Advanced Analytics**: Tracks your listening habits (Top Songs, Heatmaps, Daily Stats). Data is secured with a verified SHA-256 chain.
- 🎛️ **Multi-Engine Support**: Seamlessly switch between `mpv`, `ffplay`, and `SoX`.
- 🎵 **Multi-Format & Auto-Trim**: Supports MP3, FLAC, MP4, etc. Automatically trims audio intros to match the lyric database.
- 🛠️ **Modular Architecture**: Over 40 Python files perfectly separated for performance and stability.

---

## 📸 Screenshots

<div align="center">

| Cyberpunk Theme | Analytics Dashboard |
| :---: | :---: |
| <img src="https://i.ibb.co.com/Z6ZGxP4T/Screenshot-20261028-091324-Termux-X11.jpg" width="400"> | <img src="https://i.ibb.co.com/TNMHP4V/Screenshot-20261028-091232-Termux-X11.jpg" width="400"> |

| Live Lyrics (Spotify Style) | Sleep Timer & Settings |
| :---: | :---: |
| <img src="https://i.ibb.co.com/1GRkBS09/Screenshot-20261028-091207-Termux-X11.jpg" width="400"> | <img src="https://i.ibb.co.com/WpWJM0vk/Screenshot-20261028-091130-Termux-X11.jpg" width="400"> |

| Audio Visualizer | System Check |
| :---: | :---: |
| <img src="https://i.ibb.co.com/5hGPvnsS/Screenshot-20261028-091106-Termux-X11.jpg" width="400"> | <img src="https://i.ibb.co.com/G4022fNG/Screenshot-20261028-090906-Termux-X11.jpg" width="400"> |

<details>
<summary><b>Click to view more screenshots</b></summary>
<br>
<img src="https://i.ibb.co.com/RkV293HM/Screenshot-20261028-091300-Termux-X11.jpg" width="800">
<img src="https://i.ibb.co.com/8gy4434N/Screenshot-20261028-091243-Termux-X11.jpg" width="800">
<img src="https://i.ibb.co.com/tMsbrDYR/Screenshot-20261028-091223-Termux-X11.jpg" width="800">
<img src="https://i.ibb.co.com/zWRGVHKB/Screenshot-20261028-091151-Termux-X11.jpg" width="800">
<img src="https://i.ibb.co.com/VWhh6ZQ0/Screenshot-20261028-091118-Termux-X11.jpg" width="800">
<img src="https://i.ibb.co.com/WvV3wQSt/Screenshot-20261028-091055-Termux-X11.jpg" width="800">
</details>

</div>

---

## 🚀 Installation & Setup Guide

Since Rofpalys is built specifically for **Termux**, follow these steps carefully:

### 1. Prerequisites (Termux)
Make sure you have Python, FFmpeg, and the required libraries installed.
```bash
pkg update && pkg upgrade -y
pkg install python ffmpeg git mpv -y
pip install -r requirements.txt
```

2. Clone the Repository

```bash
git clone https://github.com/xinhailin/Rofpalys-V1.2.git
cd Rofpalys-V1.2
```

3. Install Rofpalys (Global Setup)

This command will copy the core files to usr/lib and the launcher to usr/bin.

```bash
python ~/rofpalys.py install
```

4. Install Lyric Providers

Rofpalys uses multiple databases to find the perfect synced lyrics.

```bash
rofpalys lyrics providers install
```

5. Run the Application

You can now launch Rofpalys from anywhere in your terminal!

```bash
rofpalys gui
```

---

👨‍💻 Author & Contact

Rofpalys is a solo project developed with passion (and a lot of late nights) by XinHaiLinqkn under the ANROFTY ecosystem.

· 📧 Email: xinhailinanrofty@gmail.com
· 📱 WhatsApp: +62 858-0080-9362
· 🐦 Twitter / X: @XinHaiLinqkn

<br>
<div align="center">
  <i>"Built from a 4GB RAM phone. Pushing the limits of what's possible."</i>
  <br><br>
  <b>© 2026 ANROFTY. All Rights Reserved.</b>
</div>
