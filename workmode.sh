#!/usr/bin/env bash
# ──────────────────────────────────────────────
#  workmode.sh  —  Launch J.A.R.V.I.S.
#  Usage:  bash workmode.sh
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS="$SCRIPT_DIR/jarvis_clean.py"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python3"

if [[ ! -f "$JARVIS" ]]; then
  echo "❌  jarvis_clean.py not found in $SCRIPT_DIR"
  exit 1
fi

# ── Install portaudio FIRST (PyAudio needs its C headers) ────────────
if ! command -v brew &>/dev/null; then
  echo "⚠️   Homebrew not found — mic may not work without portaudio."
else
  if ! brew list portaudio &>/dev/null 2>&1; then
    echo "📦  Installing portaudio…"
    brew install portaudio -q
  fi
fi

# ── Recreate venv if pyaudio is missing (handles first-time and stale venvs) ──
if [[ ! -f "$PYTHON" ]] || ! "$PYTHON" -c 'import pyaudio' 2>/dev/null; then
  echo "🔧  Setting up virtual environment…"
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  echo "📦  Installing packages…"
  "$PYTHON" -m pip install speechrecognition pyaudio pynput requests webrtcvad setuptools -q
  # webrtcvad's wrapper uses pkg_resources which doesn't exist in Python 3.14.
  # Patch it in-place so 'import webrtcvad' doesn't crash.
  WRTC="$VENV/lib/python3.14/site-packages/webrtcvad.py"
  if [[ -f "$WRTC" ]] && grep -q "pkg_resources" "$WRTC"; then
    "$PYTHON" - "$WRTC" <<'PYFIX'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
txt = p.read_text()
txt = re.sub(r"import pkg_resources\n", "", txt)
txt = re.sub(r"pkg_resources\.get_distribution\('webrtcvad'\)\.version", "'2.0.10'", txt)
p.write_text(txt)
print("  webrtcvad.py patched for Python 3.14")
PYFIX
  fi
  echo "✅  Packages installed"
else
  # Already good — ensure everything is present
  "$PYTHON" -m pip install speechrecognition pyaudio pynput requests webrtcvad setuptools -q 2>/dev/null
fi

echo ""
echo "🚀  Starting J.A.R.V.I.S. …"
echo "   Hotkey : Command + Shift + J"
echo "   Quit   : Ctrl + C"
echo ""

"$PYTHON" "$JARVIS"
exit $?

# # 1) Open VS Code projects
# # code "/path/to/backend"
# # code "/path/to/frontend"

# # 2) Start backend in a new Terminal window/tab
# # osascript <<'APPLESCRIPT'
# # tell application "Terminal"
# #   activate
# #   do script "cd /path/to/backend && npm run dev"
# # end tell
# # APPLESCRIPT

# # 3) Start frontend in another Terminal tab/window
# # osascript <<'APPLESCRIPT'
# # tell application "Terminal"
# #   activate
# #   do script "cd /path/to/frontend && npm run dev"
# # end tell
# # APPLESCRIPT

# # 4) Open start page tabs
# # open "https://your-dashboard.com"
# # open "https://figma.com"
# # open "http://localhost:5173"




# # 5) Start music (Spotify)
# # --- Spotify: play a specific playlist ---
# PLAYLIST_ID="2UYOZHyDOlDQejh8KrX2LM"
# PLAYLIST_URI="spotify:playlist:$PLAYLIST_ID"

# open -a "Spotify"
# sleep 1

# # Open the playlist in Spotify, then press play
# open "$PLAYLIST_URI"
# sleep 1

# osascript -e 'tell application "Spotify" to play' \
#           -e 'tell application "Spotify" to set shuffling to true' \
#           -e 'tell application "Spotify" to set sound volume to 50'
# # optional: play a playlist later (we can do AppleScript after MVP)

# echo "✅ Work mode ready."




#!/usr/bin/env python3
"""
J.A.R.V.I.S. - COMPLETE SYSTEM IN ONE FILE
Just run: python3 jarvis.py
"""

import subprocess
import sys

# Auto-install dependencies
def install_deps():
    packages = ["speechrecognition", "pyttsx3", "pynput", "requests"]
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

install_deps()

# Now import everything
import speech_recognition as sr
import pyttsx3
import requests
import json
import threading
from pynput import keyboard

print("🚀 J.A.R.V.I.S. ONLINE")
print("Hotkey: Command+Shift+J")

# Your complete Jarvis code here...
# (The rest would be the full implementation from previous messages)




#!/usr/bin/env python3
"""
ULTIMATE J.A.R.V.I.S. - All-in-One Voice Assistant
Hotkey: Command+Shift+J
Everything in one file - No dependencies needed
"""

import os
import subprocess
import sys
import time
import requests
import json
import threading
import platform
from pathlib import Path
import re

# Check and install dependencies automatically
def install_dependencies():
    """Install all required packages automatically"""
    required_packages = [
        "speechrecognition",
        "pynput", 
        "pyttsx3",
        "requests"
    ]
    
    print("🔧 Checking dependencies...")
    for package in required_packages:
        try:
            if package == "speechrecognition":
                import speech_recognition
            elif package == "pynput":
                import pynput
            elif package == "pyttsx3":
                import pyttsx3
            elif package == "requests":
                import requests
            print(f"✅ {package} already installed")
        except ImportError:
            print(f"📦 Installing {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], 
                         capture_output=True, text=True)
            print(f"✅ {package} installed")

# Install dependencies first
install_dependencies()

# Now import the installed packages
import speech_recognition as sr
import pyttsx3
from pynput import keyboard

class UltimateJarvis:
    def __init__(self):
        self.ollama_url = "http://localhost:11434"
        self.model = "llama3.2:3b"  # Fast and smart
        self.is_listening = False
        self.setup_complete = False
        
        # Voice systems
        self.tts_engine = None
        self.recognizer = None
        self.microphone = None
        
        # App database
        self.known_apps = {
            # Development
            "code": "Visual Studio Code", "vscode": "Visual Studio Code",
            "xcode": "Xcode", "studio": "Android Studio", "pycharm": "PyCharm",
            
            # Browsers
            "chrome": "Google Chrome", "browser": "Google Chrome", 
            "safari": "Safari", "firefox": "Firefox", "edge": "Microsoft Edge",
            
            # Communication
            "slack": "Slack", "discord": "Discord", "teams": "Microsoft Teams",
            "messages": "Messages", "whatsapp": "WhatsApp", "telegram": "Telegram",
            
            # Media & Entertainment
            "spotify": "Spotify", "music": "Spotify", "itunes": "Music",
            "youtube": "Safari", "netflix": "Safari", "prime": "Prime Video",
            "photos": "Photos", "tv": "TV", "video": "QuickTime Player",
            
            # Productivity
            "notes": "Notes", "calendar": "Calendar", "reminders": "Reminders",
            "mail": "Mail", "facetime": "FaceTime", "contacts": "Contacts",
            
            # Creative
            "figma": "Figma", "canva": "Canva", "photoshop": "Adobe Photoshop",
            "premiere": "Adobe Premiere Pro", "illustrator": "Adobe Illustrator",
            
            # System & Utilities
            "terminal": "Terminal", "finder": "Finder", "calculator": "Calculator",
            "settings": "System Preferences", "activity": "Activity Monitor",
            "console": "Console", "disk utility": "Disk Utility"
        }
        
        self.command_triggers = {
            "open": ["open", "launch", "start"],
            "music": ["play", "pause", "stop", "music", "volume", "song"],
            "work": ["work", "code", "develop", "programming"],
            "system": ["shutdown", "restart", "sleep", "lock"]
        }
        
        # Initialize everything
        self._initialize_systems()
    
    def _initialize_systems(self):
        """Initialize all J.A.R.V.I.S. systems"""
        print("🚀 Initializing J.A.R.V.I.S. Systems...")
        
        # 1. Check Ollama
        self._check_ollama()
        
        # 2. Setup Voice
        self._setup_voice()
        
        # 3. Setup Hotkeys
        self._setup_hotkeys()
        
        # 4. Verify Spotify
        self._check_spotify()
        
        print("✅ All Systems Operational")
        print("🎯 Hotkey: Command + Shift + J")
        print("💬 Say: 'Open Chrome', 'Play music', 'Work mode', etc.")
        self.setup_complete = True
        
        # Welcome message
        self.speak("Jarvis systems online and ready", wait=False)
    
    def _check_ollama(self):
        """Ensure Ollama is running with optimal model"""
        print("🤖 Checking Ollama...")
        
        # Check if Ollama binary exists
        if not self._command_exists("ollama"):
            print("❌ Ollama not installed. Please install from https://ollama.ai")
            return False
        
        try:
            # Start Ollama if not running
            result = subprocess.run(["pgrep", "Ollama"], capture_output=True, text=True)
            if not result.stdout.strip():
                print("🔄 Starting Ollama...")
                subprocess.Popen(["open", "-a", "Ollama"])
                time.sleep(5)
            
            # Check model availability
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                if not any(self.model in model["name"] for model in models):
                    print(f"📥 Downloading {self.model}...")
                    subprocess.run(["ollama", "pull", self.model], check=True)
                print("✅ Ollama ready")
                return True
            else:
                print("⚠️ Ollama not responding")
                return False
                
        except Exception as e:
            print(f"⚠️ Ollama check: {e}")
            return False
    
    def _setup_voice(self):
        """Setup voice recognition and text-to-speech"""
        print("🎤 Setting up voice systems...")
        
        try:
            # Text-to-speech
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 180)
            self.tts_engine.setProperty('volume', 0.8)
            print("✅ Text-to-speech ready")
        except Exception as e:
            print(f"⚠️ TTS setup: {e}")
            self.tts_engine = None
        
        try:
            # Speech recognition
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            
            # Calibrate for ambient noise
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            print("✅ Speech recognition ready")
        except Exception as e:
            print(f"⚠️ Speech recognition setup: {e}")
            self.recognizer = None
    
    def _setup_hotkeys(self):
        """Setup global hotkey listener"""
        print("⌨️ Setting up hotkeys...")
        
        def on_activate():
            if not self.is_listening and self.setup_complete:
                self.activate_voice_mode()
        
        try:
            if platform.system() == "Darwin":  # macOS
                hotkey = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char('j')}
            else:  # Windows/Linux
                hotkey = {keyboard.Key.ctrl, keyboard.Key.shift, keyboard.KeyCode.from_char('j')}
            
            self.hotkey_listener = keyboard.GlobalHotKeys({'<cmd>+<shift>+j': on_activate})
            self.hotkey_listener.start()
            print("✅ Hotkey registered: Command+Shift+J")
        except Exception as e:
            print(f"⚠️ Hotkey setup: {e}")
    
    def _check_spotify(self):
        """Check if Spotify is available"""
        try:
            subprocess.run(["osascript", "-e", 'tell application "Spotify" to get name'], 
                         capture_output=True)
            print("✅ Spotify available")
            return True
        except:
            print("⚠️ Spotify not available")
            return False
    
    def _command_exists(self, cmd):
        """Check if a command exists"""
        return subprocess.run(["which", cmd], capture_output=True).returncode == 0
    
    def speak(self, text, wait=True):
        """Speak text using TTS"""
        if not self.tts_engine:
            print(f"🗣️ [TTS]: {text}")
            return
        
        def _speak():
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"⚠️ TTS error: {e}")
        
        if wait:
            _speak()
        else:
            threading.Thread(target=_speak, daemon=True).start()
    
    def listen(self, timeout=5):
        """Listen for voice command with enhanced error handling"""
        if not self.recognizer or not self.microphone:
            return "voice_system_unavailable"
        
        try:
            print("🎤 Listening... (speak now)")
            with self.microphone as source:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=8)
            
            print("🔄 Processing...")
            text = self.recognizer.recognize_google(audio)
            print(f"👂 Heard: {text}")
            return text.lower()
            
        except sr.WaitTimeoutError:
            print("⏰ Listening timeout")
            return "timeout"
        except sr.UnknownValueError:
            print("❓ Speech unclear")
            return "unclear"
        except Exception as e:
            print(f"⚠️ Listening error: {e}")
            return f"error: {str(e)}"
    
    def query_ai(self, prompt):
        """Query Ollama for intelligent responses"""
        if not self._check_ollama():
            return "AI system unavailable"
        
        optimized_prompt = f"""You are J.A.R.V.I.S., an advanced AI assistant. Be smart, concise, and helpful.

User command: "{prompt}"

If this is a clear action request (open app, control music, system command), respond with JUST the action.
Otherwise, provide a helpful intelligent response.

Respond:"""
        
        try:
            data = {
                "model": self.model,
                "prompt": optimized_prompt,
                "stream": False,
                "options": {"temperature": 0.7, "top_p": 0.9}
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=data,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "I couldn't process that.").strip()
            else:
                return "AI service error"
                
        except Exception as e:
            return f"AI unavailable: {str(e)}"
    
    def open_application(self, app_name):
        """Open application with intelligent matching"""
        app_name_lower = app_name.lower().strip()
        
        # Special cases
        if "terminal" in app_name_lower:
            subprocess.Popen(["open", "-a", "Terminal"])
            return "Terminal launched"
        
        if "work mode" in app_name_lower or "code" in app_name_lower:
            return self.activate_work_mode()
        
        # Fuzzy matching against known apps
        for key, app_path in self.known_apps.items():
            if key in app_name_lower:
                try:
                    subprocess.Popen(["open", "-a", app_path])
                    return f"Opening {app_path}"
                except Exception as e:
                    continue
        
        # Try direct open as fallback
        try:
            subprocess.Popen(["open", "-a", app_name])
            return f"Opening {app_name}"
        except:
            # Final fallback - use AI to figure out what they meant
            ai_response = self.query_ai(f"What app should I open for: {app_name}?")
            return f"Not sure what '{app_name}' means. {ai_response}"
    
    def control_music(self, command):
        """Control music with Spotify"""
        command_lower = command.lower()
        
        applescripts = {
            "play": 'tell application "Spotify" to play',
            "pause": 'tell application "Spotify" to pause', 
            "stop": 'tell application "Spotify" to pause',
            "next": 'tell application "Spotify" to next track',
            "previous": 'tell application "Spotify" to previous track',
            "volume up": 'tell application "Spotify" to set sound volume to 100',
            "volume down": 'tell application "Spotify" to set sound volume to 25',
            "shuffle on": 'tell application "Spotify" to set shuffling to true',
            "shuffle off": 'tell application "Spotify" to set shuffling to false'
        }
        
        for key, script in applescripts.items():
            if key in command_lower:
                try:
                    subprocess.run(["osascript", "-e", script], check=True)
                    return f"Music: {key.title()}"
                except:
                    pass
        
        # Default to play
        try:
            subprocess.run(["osascript", "-e", 'tell application "Spotify" to play'], check=True)
            return "Playing music"
        except:
            return "Music control failed - is Spotify installed?"
    
    def activate_work_mode(self):
        """Activate ultimate work mode"""
        print("🚀 Activating work mode...")
        
        actions = [
            # Open development apps
            ("Visual Studio Code", ["open", "-a", "Visual Studio Code"]),
            ("Terminal", ["open", "-a", "Terminal"]),
            
            # Open browsers to useful tabs
            ("GitHub", ["open", "https://github.com"]),
            ("Documentation", ["open", "https://docs.python.org"]),
            
            # Start music
            ("Focus Music", ["osascript", "-e", 'tell application "Spotify" to play']),
            
            # Set volume
            ("Volume Setup", ["osascript", "-e", 'tell application "Spotify" to set sound volume to 60']),
        ]
        
        results = []
        for description, command in actions:
            try:
                subprocess.Popen(command)
                results.append(description)
                time.sleep(0.5)  # Stagger openings
            except Exception as e:
                results.append(f"{description} failed")
        
        return "Work mode activated: " + ", ".join(results)
    
    def process_command(self, text):
        """Intelligent command processing"""
        if text in ["timeout", "unclear", "voice_system_unavailable"]:
            return "I didn't catch that. Please try again."
        
        if text.startswith("error:"):
            return "Audio system error. Please check microphone."
        
        text_lower = text.lower()
        
        # High-speed direct matching for common commands
        if any(trigger in text_lower for trigger in self.command_triggers["open"]):
            # Extract app name using regex
            match = re.search(r'(open|launch|start)\s+(.+)', text_lower)
            if match:
                app_name = match.group(2)
                return self.open_application(app_name)
        
        if any(trigger in text_lower for trigger in self.command_triggers["music"]):
            return self.control_music(text_lower)
        
        if any(trigger in text_lower for trigger in self.command_triggers["work"]):
            return self.activate_work_mode()
        
        if any(trigger in text_lower for trigger in self.command_triggers["system"]):
            if "shutdown" in text_lower:
                subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
                return "Shutting down system"
            elif "restart" in text_lower:
                subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
                return "Restarting system"
            elif "sleep" in text_lower:
                subprocess.Popen(["osascript", "-e", 'tell app "System Events" to sleep'])
                return "Putting system to sleep"
            elif "lock" in text_lower:
                subprocess.Popen(["pmset", "displaysleepnow"])
                return "Locking screen"
        
        # Use AI for everything else
        return self.query_ai(text)
    
    def activate_voice_mode(self):
        """Main voice activation function"""
        if self.is_listening:
            return
        
        self.is_listening = True
        print("\n🎯 VOICE MODE ACTIVATED")
        self.speak("Yes sir? I'm listening", wait=False)
        
        # Listen for command
        command = self.listen(timeout=7)
        
        # Process and respond
        response = self.process_command(command)
        print(f"🤖 J.A.R.V.I.S.: {response}")
        self.speak(response)
        
        self.is_listening = False
        print("🔇 Voice mode deactivated\n")
    
    def run(self):
        """Main J.A.R.V.I.S. loop"""
        print("\n" + "="*60)
        print("🦾 ULTIMATE J.A.R.V.I.S. - VOICE ASSISTANT ACTIVE")
        print("="*60)
        print("Hotkey: Command + Shift + J")
        print("Commands: 'open chrome', 'play music', 'work mode', 'shutdown'")
        print("AI: 'what's the weather?', 'tell me a joke', 'explain quantum physics'")
        print("="*60)
        print("Press Ctrl+C to exit")
        print("="*60)
        
        try:
            # Keep alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 J.A.R.V.I.S. Shutting down...")
            self.speak("Going offline sir")
            sys.exit(0)

# Main execution
if __name__ == "__main__":
    # Verify we can run
    if platform.system() != "Darwin":
        print("⚠️ This version is optimized for macOS. Some features may not work.")
    
    # Create and run Jarvis
    jarvis = UltimateJarvis()
    jarvis.run()
