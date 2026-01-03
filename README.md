# 🤖 ANDROS - Local AI Assistant (Hybrid HUD)

**Andros** adalah asisten AI berbasis suara yang berjalan 100% lokal (Offline-Capable) di PC Anda. Menggabungkan kekuatan **Ollama** (Otak), **Faster-Whisper** (Telinga), dan antarmuka Sci-Fi futuristik yang terisolasi.

![Andros HUD Screenshot](https://via.placeholder.com/800x450.png?text=ANDROS+System+V.18)

## ✨ Fitur Utama
* **🧠 Local Intelligence:** Menggunakan LLM via Ollama (`gemma2`, `llama3`, dll) untuk privasi total.
* **🗣️ Natural Voice Interaction:** Mendengar menggunakan *Faster-Whisper* (CUDA Accelerated).
* **🔇 Anti-Echo System:** Mode *Half-Duplex* cerdas (Mic mati otomatis saat AI berbicara) untuk mencegah AI berbicara sendiri.
* **💻 Isolated Secure UI:** Antarmuka berjalan di jendela browser khusus (App Mode) yang terpisah dari browser kerja Anda.
* **🔊 Offline TTS:** Menggunakan engine suara bawaan Windows (Cepat & Tanpa Internet).
* **📊 Hardware Monitor:** Memantau CPU, RAM, dan GPU (NVIDIA) secara *real-time*.

## 🛠️ Prasyarat (Requirements)

Pastikan Anda telah menginstal:
1.  **Python 3.10 / 3.11**
2.  **Ollama** ([Download di sini](https://ollama.com/))
3.  **Microsoft Edge** atau **Google Chrome** (Untuk UI).
4.  **NVIDIA GPU** (Sangat disarankan untuk performa Whisper & LLM).

## 📦 Instalasi

1.  **Clone/Download repository ini.**
2.  **Buat Virtual Environment (Disarankan):**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
3.  **Install Library Python:**
    ```bash
    pip install fastapi uvicorn[standard] faster-whisper pyttsx3 colorama SpeechRecognition websockets psutil GPUtil duckduckgo-search requests
    ```
    *(Catatan: Anda mungkin perlu menginstall PyAudio secara manual via `.whl` jika pip gagal).*

4.  **Siapkan Model Ollama:**
    Buka terminal baru dan download model yang diinginkan (sesuaikan dengan config di `main.py`):
    ```bash
    ollama pull gemma2:2b
    # ATAU
    ollama pull llama3:8b
    ```

## 🚀 Cara Menjalankan

1.  **Langkah 1: Jalankan Server Ollama**
    Buka terminal (CMD/PowerShell), ketik:
    ```bash
    ollama serve
    ```
    *Biarkan terminal ini tetap terbuka.*

2.  **Langkah 2: Jalankan Andros**
    Buka terminal proyek (pastikan venv aktif), ketik:
    ```bash
    python main.py
    ```

3.  **Selesai!**
    * Jendela UI Andros akan muncul otomatis (Isolated Mode).
    * Tunggu hingga status berubah menjadi **"OLLAMA CONNECTED"**.
    * Mulai berbicara dengan sapaan (misal: *"Halo Andros"*).

## ⚙️ Konfigurasi (`main.py`)

Anda dapat mengubah pengaturan di bagian atas file `main.py`:

```python
@dataclass
class Config:
    AI_NAME: str = "Andros"
    OLLAMA_MODEL: str = "gemma2:2b"  # Ganti nama model disini
    MIC_ENERGY_THRESHOLD: int = 300  # Sensitivitas Mic (Makin kecil makin sensitif)
