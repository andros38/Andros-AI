import os
# Matikan log spam
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

import asyncio
import threading
import json
import requests
import time
import glob
import signal
import sys
import logging
import speech_recognition as sr
import queue 
import re    
import random 
import pyttsx3 
import subprocess # Untuk browser terpisah
import tempfile   # Untuk profil browser sementara
import shutil     # Untuk hapus profil sementara

from datetime import datetime
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

# Third Party Libraries
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from faster_whisper import WhisperModel
from colorama import Fore, Style, init
import webbrowser
import psutil
import GPUtil
from duckduckgo_search import DDGS

# Initialize Colorama
init(autoreset=True)

# --- 1. CONFIGURATION ---
@dataclass
class Config:
    AI_NAME: str = "Andros"
    OLLAMA_MODEL: str = "gemma3:4b" 
    MIC_ENERGY_THRESHOLD: int = 300 # Normal Sensitivity
    SEARCH_TIMEOUT: int = 15
    MAX_HISTORY: int = 6
    CACHE_DURATION: int = 300 

config = Config()

# GLOBAL FLAGS
IS_AI_SPEAKING = False 
browser_process = None # Handle untuk proses browser
temp_profile_dir = None # Handle untuk folder profil sementara

# --- 2. OFFLINE TTS WORKER ---
tts_queue = queue.Queue()

def tts_worker():
    global IS_AI_SPEAKING
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 175)
        voices = engine.getProperty('voices')
        for voice in voices:
            if "Indonesia" in voice.name or "ID" in voice.id:
                engine.setProperty('voice', voice.id)
                break
        print(Fore.GREEN + "✅ Offline TTS Engine Ready.")
    except Exception as e:
        print(Fore.RED + f"❌ TTS Init Failed: {e}")
        return

    while True:
        text = tts_queue.get()
        if text is None: break
        
        try:
            IS_AI_SPEAKING = True
            print(Fore.YELLOW + f"🔊 Andros: {text}")
            engine.say(text)
            engine.runAndWait()
            time.sleep(0.5)
        except Exception as e:
            print(Fore.RED + f"❌ TTS Error: {e}")
        finally:
            IS_AI_SPEAKING = False
            tts_queue.task_done()

threading.Thread(target=tts_worker, daemon=True).start()

def speak(text):
    text_clean = re.sub(r'[^\w\s,?!.:]', '', text)
    tts_queue.put(text_clean)

# --- 3. SYSTEM SETUP ---
def setup_logging():
    logger = logging.getLogger('Andros')
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler('andros_system.log', maxBytes=5*1024*1024, backupCount=2)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger

logger = setup_logging()
app = FastAPI()
main_event_loop = None 
conversation_history = [] 
search_cache = {} 

class WhisperProcessor:
    _model = None
    @classmethod
    def get_model(cls):
        if cls._model is None:
            print(Fore.CYAN + "🚀 Memuat Whisper Model...")
            try:
                cls._model = WhisperModel("medium", device="cuda", compute_type="float16", cpu_threads=4)
                print(Fore.GREEN + "✅ Whisper dimuat di GPU (CUDA).")
            except Exception as e:
                print(Fore.YELLOW + f"⚠️ GPU Error, Fallback ke CPU: {e}")
                cls._model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
        return cls._model

# --- 4. CLEANUP & BROWSER CONTROL ---
class AndrosSystem:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, sig, frame):
        print(Fore.YELLOW + "\n🛑 Shutting down Andros System...")
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        global browser_process, temp_profile_dir
        
        # 1. Matikan Browser UI
        if browser_process:
            print(Fore.CYAN + "🔌 Menutup Interface...")
            try:
                browser_process.terminate() # Matikan proses browser khusus ini
                browser_process.wait(timeout=2)
            except:
                try: browser_process.kill()
                except: pass
        
        # 2. Hapus Profil Browser Sementara (Biar laptop gak penuh sampah)
        if temp_profile_dir and os.path.exists(temp_profile_dir):
            try:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
            except: pass

        # 3. Hapus Wav Temp
        for file in glob.glob("temp_*.wav"):
            try: os.remove(file)
            except: pass
            
        print(Fore.GREEN + "✅ System Cleaned & UI Closed.")

system_manager = AndrosSystem()

# --- 5. HTML UI ---
html = """
<!DOCTYPE html>
<html>
<head>
    <title>ANDROS INTERFACE</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&family=Share+Tech+Mono&display=swap');
        body { background-color: #020202; color: #00ffff; font-family: 'Share Tech Mono', monospace; margin: 0; overflow: hidden; height: 100vh; width: 100vw; background-image: radial-gradient(circle at 50% 50%, #051515 0%, #000000 80%), linear-gradient(rgba(0, 255, 255, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 255, 255, 0.02) 1px, transparent 1px); background-size: 100% 100%, 40px 40px, 40px 40px; }
        .hud-container { display: grid; grid-template-rows: 60px 1fr 40px; grid-template-columns: 320px 1fr 320px; height: 100vh; width: 100vw; padding: 15px; box-sizing: border-box; gap: 15px; }
        .header { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid rgba(0,255,255,0.3); background: rgba(0,0,0,0.5); padding: 0 10px; }
        .title { font-family: 'Rajdhani', sans-serif; font-size: 24px; font-weight: bold; letter-spacing: 2px; }
        .clock { font-size: 18px; color: #fff; }
        .footer { grid-column: 1 / -1; border-top: 1px solid rgba(0,255,255,0.2); display: flex; align-items: center; font-size: 12px; color: #0f0; background: #000; padding: 0 10px; }
        .console-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #00ff00; }
        .panel { background: rgba(0, 20, 25, 0.4); border: 1px solid rgba(0, 255, 255, 0.2); backdrop-filter: blur(4px); padding: 15px; display: flex; flex-direction: column; position: relative; overflow: hidden; }
        .panel::before { content: ''; position: absolute; top: 0; left: 0; width: 10px; height: 10px; border-top: 2px solid #00ffff; border-left: 2px solid #00ffff; }
        .panel::after { content: ''; position: absolute; bottom: 0; right: 0; width: 10px; height: 10px; border-bottom: 2px solid #00ffff; border-right: 2px solid #00ffff; }
        h3 { margin: 0 0 15px 0; font-size: 16px; color: rgba(0,255,255,0.8); border-bottom: 1px dashed rgba(0,255,255,0.3); padding-bottom: 5px; }
        .stat-row { margin-bottom: 15px; }
        .label { font-size: 12px; color: #888; display: flex; justify-content: space-between; margin-bottom: 3px; }
        .bar-bg { width: 100%; height: 6px; background: rgba(255,255,255,0.1); }
        .bar-fill { height: 100%; width: 0%; transition: width 0.3s ease; }
        .right-panel { display: flex; flex-direction: column; min-height: 0; }
        .chat-container { flex: 1; overflow-y: auto; padding-right: 5px; display: flex; flex-direction: column; gap: 10px; min-height: 0; scroll-behavior: smooth; }
        .chat-container::-webkit-scrollbar { width: 4px; }
        .chat-container::-webkit-scrollbar-thumb { background: #00ffff; border-radius: 2px; }
        .chat-container::-webkit-scrollbar-track { background: rgba(0,0,0,0.3); }
        .msg { padding: 8px; border-left: 2px solid; font-size: 14px; line-height: 1.4; animation: fadeIn 0.3s ease; }
        .msg-user { border-color: #fff; background: rgba(255,255,255,0.05); color: #ddd; }
        .msg-ai { border-color: #00ffff; background: rgba(0,255,255,0.05); color: #00ffff; }
        .msg-label { font-size: 10px; font-weight: bold; margin-bottom: 2px; display: block; opacity: 0.7; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        .center-panel { display: flex; justify-content: center; align-items: center; position: relative; }
        .hud-circle { position: relative; width: 350px; height: 350px; display: flex; justify-content: center; align-items: center; }
        .ring { position: absolute; border-radius: 50%; transition: all 0.5s ease; }
        .r1 { width: 100%; height: 100%; border: 1px dashed rgba(0,255,255,0.3); animation: spin 20s linear infinite; }
        .r2 { width: 85%; height: 85%; border: 2px solid transparent; border-top: 2px solid currentColor; border-bottom: 2px solid currentColor; animation: spin 8s linear infinite; }
        .r3 { width: 70%; height: 70%; border: 4px dotted currentColor; border-left: 4px solid transparent; border-right: 4px solid transparent; animation: spin-rev 5s linear infinite; }
        .core-text { position: absolute; font-family: 'Rajdhani', sans-serif; font-size: 24px; font-weight: bold; letter-spacing: 3px; z-index: 10; text-shadow: 0 0 15px currentColor; }
        .state-listening { color: #ff0055; } .state-listening .r2 { box-shadow: 0 0 20px #ff0055; }
        .state-speaking { color: #00ffff; } .state-speaking .r2 { animation: pulse 1s infinite; box-shadow: 0 0 30px #00ffff; } .state-speaking .r3 { border-style: solid; }
        .state-thinking { color: #ffaa00; } .state-thinking .r2 { animation: spin 0.5s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } } @keyframes spin-rev { 100% { transform: rotate(-360deg); } } @keyframes pulse { 50% { transform: scale(1.05) rotate(180deg); } }
        @media (max-width: 1200px) { .hud-container { grid-template-columns: 260px 1fr 260px; } .hud-circle { width: 280px; height: 280px; } }
        @media (max-width: 900px) { .hud-container { grid-template-columns: 1fr; grid-template-rows: 50px 200px 1fr 200px 30px; gap: 10px; } .center-panel { order: 2; } .right-panel { order: 3; } .left-panel { order: 4; display: none; } }
    </style>
</head>
<body>
    <div class="hud-container">
        <div class="header">
            <div class="title">ANDROS <span style="font-size:0.6em; opacity:0.7;">// OS.18.0 SECURE UI</span></div>
            <div class="clock" id="clock">00:00</div>
        </div>
        <div class="panel left-panel">
            <h3>DIAGNOSTICS</h3>
            <div class="stat-row"><div class="label"><span>CPU LOAD</span><span id="cpu-txt">0%</span></div><div class="bar-bg"><div class="bar-fill" id="cpu-bar" style="background:#00ffff; box-shadow:0 0 5px #00ffff;"></div></div></div>
            <div class="stat-row"><div class="label"><span>RAM USAGE</span><span id="ram-txt">0%</span></div><div class="bar-bg"><div class="bar-fill" id="ram-bar" style="background:#ff00ff; box-shadow:0 0 5px #ff00ff;"></div></div></div>
            <div class="stat-row"><div class="label"><span>GPU (RTX 4060)</span><span id="gpu-txt">0%</span></div><div class="bar-bg"><div class="bar-fill" id="gpu-bar" style="background:#ffff00; box-shadow:0 0 5px #ffff00;"></div></div></div>
            <div style="margin-top:auto; font-size:10px; color:#666;">LATENCY: 12ms<br>TEMP: OPTIMAL<br>SECURE CONN: ACTIVE</div>
        </div>
        <div class="center-panel">
            <div id="hud-wrapper" class="hud-circle state-listening">
                <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>
                <div class="core-text" id="status-text">LISTENING</div>
            </div>
        </div>
        <div class="panel right-panel">
            <h3>COMMUNICATION LOG</h3>
            <div class="chat-container" id="chat-box">
                <div class="msg msg-ai"><span class="msg-label">ANDROS</span>Secure Interface Loaded. Mic Active.</div>
            </div>
        </div>
        <div class="footer">
            <span style="margin-right:10px;">> CONSOLE:</span>
            <div class="console-text" id="console-log">Initializing...</div>
        </div>
    </div>
    <script>
        const ws = new WebSocket("ws://localhost:8000/ws");
        const hudWrapper = document.getElementById('hud-wrapper');
        const statusText = document.getElementById('status-text');
        const chatBox = document.getElementById('chat-box');
        const consoleLog = document.getElementById('console-log');
        setInterval(() => { const d = new Date(); document.getElementById('clock').innerText = d.toLocaleTimeString('en-US', {hour12:false}); }, 1000);
        function scrollToBottom() { chatBox.scrollTop = chatBox.scrollHeight; }
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.type === 'state') {
                hudWrapper.classList.remove('state-listening', 'state-speaking', 'state-thinking');
                if(data.val === 'listening') { hudWrapper.classList.add('state-listening'); statusText.innerText = "LISTENING"; }
                else if(data.val === 'speaking') { hudWrapper.classList.add('state-speaking'); statusText.innerText = "ACTIVE"; }
                else if(data.val === 'thinking') { hudWrapper.classList.add('state-thinking'); statusText.innerText = "PROCESSING"; }
            } else if (data.type === 'log') {
                const msgDiv = document.createElement('div');
                if (data.role === 'user-text') { msgDiv.className = "msg msg-user"; msgDiv.innerHTML = `<span class="msg-label">USER</span>${data.text}`; }
                else { msgDiv.className = "msg msg-ai"; msgDiv.innerHTML = `<span class="msg-label">ANDROS</span>${data.text}`; }
                chatBox.appendChild(msgDiv); scrollToBottom(); 
            } else if (data.type === 'console') {
                consoleLog.innerText = data.text;
                consoleLog.style.color = "#00ff00";
            } else if (data.type === 'stats') {
                document.getElementById('cpu-txt').innerText = data.cpu + "%"; document.getElementById('cpu-bar').style.width = data.cpu + "%";
                document.getElementById('ram-txt').innerText = data.ram + "%"; document.getElementById('ram-bar').style.width = data.ram + "%";
                if (data.gpu_load) { document.getElementById('gpu-txt').innerText = data.gpu_load + "%"; document.getElementById('gpu-bar').style.width = data.gpu_load + "%"; }
            }
        };
    </script>
</body>
</html>
"""

# --- 6. BACKEND SERVER ---
class ConnectionManager:
    def __init__(self): self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket): await websocket.accept(); self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket): self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_json(message)
            except: pass
manager = ConnectionManager()

@app.get("/")
async def get(): return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    await manager.connect(websocket)
    if len(manager.active_connections) == 1:
        threading.Thread(target=system_monitor_loop, daemon=True).start()
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- 7. HELPER FUNCTIONS ---
def system_monitor_loop():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            gpus = GPUtil.getGPUs()
            gpu = round(gpus[0].load * 100, 1) if gpus else 0
            if main_event_loop and manager.active_connections:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "stats", "cpu": cpu, "ram": ram, "gpu_load": gpu}), 
                    main_event_loop
                )
        except: pass
        time.sleep(1)

def send_to_ui(message_dict):
    if main_event_loop and manager.active_connections:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message_dict), main_event_loop)

def build_prompt(user_text, search_result, history):
    now = datetime.now()
    NAMA_HARI = {"Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu", "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"}
    hari_indo = NAMA_HARI[now.strftime("%A")]
    jam_sekarang = now.strftime("%H:%M")
    
    system_prompt = (
        f"Kamu adalah Andros, AI cerdas. [KONTEKS: {hari_indo}, {jam_sekarang}]. "
        "ATURAN: Jawab singkat, padat, dan jelas (Max 2 kalimat). "
        "Gunakan bahasa Indonesia yang santai, sopan, dan netral (jangan panggil Bos/Sir, panggil 'Kawan' atau langsung jawab saja)."
    )
    hist_str = "\n".join(history[-config.MAX_HISTORY:]) 
    full_prompt = f"{system_prompt}\n\nRIWAYAT:\n{hist_str}\n\nUser: {user_text}\nAndros:"
    return full_prompt

def check_ollama_manual():
    print(Fore.CYAN + "⚙️ Mengecek koneksi ke Ollama...")
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        if res.status_code == 200:
            print(Fore.GREEN + "✅ Koneksi Ollama Berhasil!")
            return True
    except requests.exceptions.ConnectionError:
        print(Fore.RED + "❌ ERROR FATAL: Ollama TIDAK TERDETEKSI!")
        print(Fore.YELLOW + "👉 WAJIB: Buka terminal baru -> ketik 'ollama serve'")
        return False
    except Exception: return False

# --- 8. ISOLATED BROWSER LAUNCHER (NEW) ---
def open_browser_isolated():
    global browser_process, temp_profile_dir
    
    url = "http://localhost:8000"
    
    # 1. Buat folder profil sementara (agar tidak ganggu browser utama)
    temp_profile_dir = tempfile.mkdtemp()
    
    # 2. Deteksi Browser (Prioritas: Edge -> Chrome)
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    
    browser_exe = None
    
    # Cek Edge
    for path in edge_paths:
        if os.path.exists(path):
            browser_exe = path
            break
            
    # Kalau Edge gak ada, Cek Chrome
    if not browser_exe:
        for path in chrome_paths:
            if os.path.exists(path):
                browser_exe = path
                break
    
    if browser_exe:
        print(Fore.CYAN + f"🚀 Membuka Secure UI dengan: {os.path.basename(browser_exe)}")
        try:
            # Arguments untuk App Mode + Isolated Profile
            args = [
                browser_exe,
                f"--app={url}",                # Mode Aplikasi (Tanpa Address Bar)
                f"--user-data-dir={temp_profile_dir}", # Profil Terpisah (PENTING!)
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1200,800"
            ]
            
            # Jalankan Browser sebagai Subprocess
            browser_process = subprocess.Popen(args)
            return
        except Exception as e:
            print(Fore.RED + f"⚠️ Gagal membuka Isolated Browser: {e}")
            
    # Fallback ke browser biasa jika semua gagal
    print(Fore.YELLOW + "⚠️ Browser exe tidak ditemukan, menggunakan default...")
    webbrowser.open(url)

# --- 9. MAIN LOGIC ---
def jarvis_loop():
    whisper = WhisperProcessor.get_model()
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = config.MIC_ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True 
    
    HALLUCINATIONS = [
        "terima kasih", "thank you", "subtitles", "percakapan santai",
        "blas", "masak", "amara", "teks", "audio", "siap", "oke", "ok"
    ]

    with sr.Microphone() as source:
        print(Fore.CYAN + "🎤 Sistem Andros Online (Mic Active).")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        
        time.sleep(1)
        send_to_ui({"type": "console", "text": "OLLAMA CONNECTED. SYSTEMS READY."})
        
        while system_manager.running:
            if IS_AI_SPEAKING:
                time.sleep(0.5)
                continue

            temp_wav = f"temp_{int(time.time())}.wav"
            try:
                send_to_ui({"type": "state", "val": "listening"})
                audio = recognizer.listen(source, timeout=None)
                
                if IS_AI_SPEAKING: continue 

                with open(temp_wav, "wb") as f: f.write(audio.get_wav_data())

                send_to_ui({"type": "state", "val": "thinking"})
                segments, info = whisper.transcribe(temp_wav, beam_size=1, language="id", vad_filter=True, initial_prompt="Percakapan santai.")
                user_text = "".join([s.text for s in segments]).strip()

                try: os.remove(temp_wav)
                except: pass

                clean_input = re.sub(r'[^\w\s]', '', user_text.lower())
                if len(clean_input) < 3:
                    if clean_input not in ["hai", "hi", "tes"]:
                        send_to_ui({"type": "state", "val": "listening"})
                        continue

                is_halu = False
                for bad in HALLUCINATIONS:
                    if bad in clean_input and len(clean_input) < 15:
                        is_halu = True
                        break
                if is_halu: 
                    send_to_ui({"type": "state", "val": "listening"})
                    continue

                print(Fore.WHITE + f"User: {user_text}")
                send_to_ui({"type": "log", "text": user_text, "role": "user-text"})

                prompt = build_prompt(user_text, "", conversation_history)
                payload = {"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"num_ctx": 2048}}
                
                try:
                    res = requests.post("http://localhost:11434/api/generate", json=payload, timeout=config.SEARCH_TIMEOUT+30)
                    if res.status_code == 200:
                        reply = res.json().get("response", "Error.").replace("Andros:", "").strip()
                    else:
                        reply = f"Error: {res.status_code}"
                except Exception as e:
                    reply = "Maaf, ada gangguan."

                conversation_history.append(f"User: {user_text}")
                conversation_history.append(f"Andros: {reply}")

                send_to_ui({"type": "state", "val": "speaking"})
                send_to_ui({"type": "log", "text": reply, "role": "ai-text"})
                speak(reply)
                
            except Exception as e:
                send_to_ui({"type": "state", "val": "listening"})

if __name__ == "__main__":
    system_manager.cleanup()
    
    if check_ollama_manual():
        speak("Sistem Andros Online.")
        t = threading.Thread(target=jarvis_loop); t.daemon = True; t.start()
        
        # GANTI PEMBUKA BROWSER BIASA DENGAN YANG ISOLATED
        threading.Timer(1.5, open_browser_isolated).start()
        
        try:
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="critical")
        except KeyboardInterrupt:
            system_manager.cleanup()
    else:
        print(Fore.RED + "Program dihentikan karena Ollama tidak aktif.")
        sys.exit(1)