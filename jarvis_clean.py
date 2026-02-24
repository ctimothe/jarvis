#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Voice Assistant
Trigger : Command + Shift + J
Model   : tinyllama (via Ollama)
TTS     : macOS native `say` command (no pyttsx3 issues)
"""

import os
import sys
import time
import re
import threading
import subprocess
import platform

# Packages are installed by workmode.sh into .venv before this script runs.
# Running directly? Use:  bash workmode.sh
try:
    import requests
    import speech_recognition as sr
    import pyaudio
    import webrtcvad
    import collections
    from pynput import keyboard
except ImportError as e:
    print(f"❌  Missing dependency: {e}")
    print("   Run via:  bash workmode.sh  (it sets up the venv for you)")
    sys.exit(1)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OLLAMA_URL        = "http://localhost:11434"
MODEL             = "llama3.1:8b"
HOME              = os.path.expanduser("~")

# ── SmartMic constants ────────────────────────────────────────────────────────
VAD_SAMPLE_RATE      = 16000   # Hz  — required by webrtcvad
VAD_FRAME_MS         = 30      # ms per frame  (10 / 20 / 30 only)
VAD_FRAME_SAMPLES    = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)   # 480 samples
VAD_AGGRESSIVENESS   = 2       # 0=lenient … 3=aggressive non-speech filter
PRE_ROLL_FRAMES      = 10      # ~300ms buffered before speech start (catches first syllable)
SILENCE_END_FRAMES   = 30      # ~900ms of silence → end of utterance  (ChatGPT-like)
MIN_SPEECH_FRAMES    = 3       # ignore clicks / pops shorter than this
MAX_RECORD_SECONDS   = 30      # safety ceiling
STARTUP_TIMEOUT_S    = 8       # give up if no speech within this time


# ─────────────────────────────────────────────
# TTS  — macOS `say`, interruptible
# ─────────────────────────────────────────────
_say_proc: subprocess.Popen | None = None

def stop_speaking():
    """Kill any currently running `say` process."""
    global _say_proc
    if _say_proc and _say_proc.poll() is None:
        _say_proc.terminate()
        _say_proc = None

def speak(text: str, wait: bool = False):
    """Interrupt previous speech, then speak new text.
    wait=True blocks until audio finishes — always use before opening the mic
    so Jarvis doesn't hear its own voice.
    """
    global _say_proc
    stop_speaking()
    print(f"🗣  Jarvis: {text}")
    _say_proc = subprocess.Popen(["say", "-r", "185", text])
    if wait:
        _say_proc.wait()


# ─────────────────────────────────────────────
# OLLAMA
# ─────────────────────────────────────────────
def _ollama_alive() -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def _start_ollama():
    if not _ollama_alive():
        print("🔄 Starting Ollama…")
        subprocess.Popen(["open", "-a", "Ollama"])
        for _ in range(12):
            time.sleep(1)
            if _ollama_alive():
                print("✅ Ollama online")
                return
        print("⚠️  Ollama did not start — AI answers will be unavailable.")


def _chat(system: str, user: str, temperature: float = 0.3,
          stop: list | None = None, timeout: int = 40) -> str:
    """Shared Ollama /api/chat call used by every component."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "stop": stop or ["User:", "Human:", "\nUser", "\nHuman", "Assistant:"],
        },
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        if r.status_code == 200:
            raw = r.json().get("message", {}).get("content", "").strip()
            raw = re.split(r'\n(?:User|Human|Assistant)\s*:', raw, maxsplit=1)[0].strip()
            return raw
        return f"Ollama error {r.status_code}."
    except requests.exceptions.Timeout:
        return "The AI took too long, please try again."
    except Exception as e:
        return f"AI error: {e}"


def ask_ai(prompt: str) -> str:
    """General Q&A. Strictly forbidden from pretending to perform computer actions."""
    if not _ollama_alive():
        return "The AI is offline. Make sure Ollama is running."
    return _chat(
        system=(
            "You are J.A.R.V.I.S., a voice assistant. "
            "Answer in plain spoken English, maximum 3 sentences, no markdown. "
            "CRITICAL: You cannot perform actions on the computer yourself. "
            "Only the Python code beneath you can open apps, create files, run commands, etc. "
            "If asked to do something on the computer, say you will pass it to the system. "
            "NEVER claim you created, opened, deleted, or performed any action. "
            "NEVER write 'User:', 'Human:', or simulate a dialogue."
        ),
        user=prompt,
        temperature=0.4,
    )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    return result.stdout.strip()


# ─────────────────────────────────────────────
# SMART MIC  — WebRTC VAD-based listener
# ─────────────────────────────────────────────
class SmartMic:
    def __init__(self):
        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self._pa  = pyaudio.PyAudio()
        self._rec = sr.Recognizer()

    def listen(self) -> str:
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=VAD_SAMPLE_RATE,
            input=True,
            frames_per_buffer=VAD_FRAME_SAMPLES,
        )
        # Ring buffer: saves the N frames *before* speech starts
        # so the first syllable is never clipped
        pre_roll     = collections.deque(maxlen=PRE_ROLL_FRAMES)
        speech_buf   = []
        triggered    = False
        silence_ct   = 0
        consec_voice = 0    # consecutive voiced frames needed to trigger
        total        = 0
        max_frames   = int(MAX_RECORD_SECONDS * 1000 / VAD_FRAME_MS)
        wait_frames  = int(STARTUP_TIMEOUT_S  * 1000 / VAD_FRAME_MS)

        print("👂 Listening (VAD)…")
        try:
            while total < max_frames:
                try:
                    frame = stream.read(VAD_FRAME_SAMPLES, exception_on_overflow=False)
                except Exception:
                    break
                total += 1
                is_speech = self._vad.is_speech(frame, VAD_SAMPLE_RATE)

                if not triggered:
                    pre_roll.append(frame)
                    consec_voice = (consec_voice + 1) if is_speech else 0
                    if consec_voice >= MIN_SPEECH_FRAMES:
                        triggered = True
                        speech_buf.extend(pre_roll)   # include pre-roll
                        silence_ct = 0
                        print("🗨  Capturing speech…")
                    elif total > wait_frames:          # no speech in time
                        break
                else:
                    speech_buf.append(frame)
                    if not is_speech:
                        silence_ct += 1
                        if silence_ct >= SILENCE_END_FRAMES:
                            print("⏹  End of speech.")
                            break
                    else:
                        silence_ct = 0
        finally:
            stream.stop_stream()
            stream.close()

        if not triggered or len(speech_buf) < MIN_SPEECH_FRAMES:
            return ""

        raw = b"".join(speech_buf)
        audio = sr.AudioData(raw, VAD_SAMPLE_RATE, 2)  # 2 bytes = Int16
        try:
            print("🔄 Recognising…")
            text = self._rec.recognize_google(audio, language="en-US")
            print(f'📝 You said: "{text}"')
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            speak("Speech service unavailable.")
            return ""
        except Exception as e:
            print(f"⚠️  STT error: {e}")
            return ""


# ─────────────────────────────────────────────
# APP DICT
# ─────────────────────────────────────────────
KNOWN_APPS = {
    "chrome":            "Google Chrome",
    "browser":           "Google Chrome",
    "safari":            "Safari",
    "firefox":           "Firefox",
    "vscode":            "Visual Studio Code",
    "visual studio":     "Visual Studio Code",
    "code":              "Visual Studio Code",
    "terminal":          "Terminal",
    "iterm":             "iTerm",
    "spotify":           "Spotify",
    "music":             "Spotify",
    "slack":             "Slack",
    "discord":           "Discord",
    "finder":            "Finder",
    "notes":             "Notes",
    "calendar":          "Calendar",
    "mail":              "Mail",
    "figma":             "Figma",
    "xcode":             "Xcode",
    "pycharm":           "PyCharm",
    "calculator":        "Calculator",
    "settings":          "System Preferences",
    "activity monitor":  "Activity Monitor",
    "photos":            "Photos",
    "messages":          "Messages",
    "facetime":          "FaceTime",
    "whatsapp":          "WhatsApp",
    "notion":            "Notion",
    "zoom":              "zoom.us",
    "teams":             "Microsoft Teams",
    "obsidian":          "Obsidian",
    "arc":               "Arc",
}


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────
def handle_open(query: str) -> str:
    q = query.lower()
    m = re.search(r'\b(?:open|launch|start)\s+(.+)', q)
    target = m.group(1).strip() if m else q

    for key, app in KNOWN_APPS.items():
        if key in target:
            res = subprocess.run(["open", "-a", app], capture_output=True)
            if res.returncode == 0:
                return f"Opening {app}."
            break

    # Try as-is
    res = subprocess.run(["open", "-a", target], capture_output=True)
    if res.returncode == 0:
        return f"Opening {target}."

    return f"I couldn't find an app called {target}."


def handle_music(query: str) -> str:
    q = query.lower()
    actions = {
        "pause":       'tell application "Spotify" to pause',
        "stop":        'tell application "Spotify" to pause',
        "next":        'tell application "Spotify" to next track',
        "previous":    'tell application "Spotify" to previous track',
        "skip":        'tell application "Spotify" to next track',
        "volume up":   'tell application "Spotify" to set sound volume to 100',
        "volume down": 'tell application "Spotify" to set sound volume to 25',
        "shuffle":     'tell application "Spotify" to set shuffling to true',
    }
    for keyword, script in actions.items():
        if keyword in q:
            _osascript(script)
            return f"Done — {keyword}."
    # default: play / resume
    _osascript('tell application "Spotify" to play')
    return "Playing music."


def handle_work_mode() -> str:
    for app in ["Visual Studio Code", "Terminal", "Google Chrome"]:
        subprocess.Popen(["open", "-a", app])
        time.sleep(0.4)
    _osascript('tell application "Spotify" to play')
    return "Work mode on. Launching VS Code, Terminal, and Chrome."


def handle_system(query: str) -> str:
    q = query.lower()
    if "sleep" in q:
        subprocess.Popen(["pmset", "sleepnow"])
        return "Going to sleep."
    if "lock" in q:
        _osascript('tell application "System Events" to keystroke "q" using {command down, control down}')
        return "Screen locked."
    if "shutdown" in q or "shut down" in q:
        speak("Shutting down in 5 seconds.")
        time.sleep(5)
        _osascript('tell app "System Events" to shut down')
        return ""
    if "restart" in q or "reboot" in q:
        speak("Restarting in 5 seconds.")
        time.sleep(5)
        _osascript('tell app "System Events" to restart')
        return ""
    return ask_ai(query)


# ─────────────────────────────────────────────
# SHELL ENGINE
# ─────────────────────────────────────────────

_global_mic: SmartMic | None = None

_BLOCKED_PATHS = [
    "/System", "/bin", "/sbin", "/usr/bin", "/usr/sbin",
    "/usr/lib", "/usr/libexec", "/private/etc",
    "/Library/Apple", "/dev",
]

_BLOCKED_RE = [re.compile(p, re.IGNORECASE) for p in [
    r'\bsudo\b',
    r'\bdd\s+if=',
    r'\bmkfs\b',
    r':\(\)\s*\{',
    r'curl\s+[^\|]+\|\s*(ba|z)?sh',
    r'wget\s+[^\|]+\|\s*(ba|z)?sh',
    r'\bchmod\s+[0-9]+\s+/',
    r'\bchown\s+\S+\s+/',
    r'\blaunchctl\s+(unload|disable|remove)\b',
    r'>\s*/dev/(?:r?disk[0-9]|zero)',
    r'\brm\s+-[a-z]*r[a-z]*f\s+/',
]]

_DESTRUCTIVE_RE = re.compile(r'\b(rm\b|rmdir\b|killall\b|pkill\b)', re.IGNORECASE)

def _safe_check(cmd: str) -> tuple:
    for pat in _BLOCKED_RE:
        if pat.search(cmd):
            return False, "blocked pattern"
    for path in _BLOCKED_PATHS:
        if re.search(re.escape(path) + r'(?:[/\s"\'\\]|$)', cmd):
            return False, f"protected path: {path}"
    if re.search(r'\brm\b', cmd, re.IGNORECASE):
        for p in re.findall(r'["\']?(/[^\s"\';&|]+)', cmd):
            if not p.startswith(HOME):
                return False, "rm outside home"
    return True, ""


def _generate_shell_cmd(natural: str) -> str:
    """Translate natural language into one zsh command via the LLM."""
    cmd = _chat(
        system=(
            "You are a macOS zsh command generator.\n"
            f"User home: {HOME}\n"
            "Output ONE raw shell command only. No explanation, no markdown, no backticks.\n"
            "Rules:\n"
            "Never use sudo.\n"
            "Use full absolute paths, never ~.\n"
            f"To delete: osascript -e 'tell app \"Finder\" to delete POSIX file \"/full/path\"'\n"
            "To create folder: mkdir -p /full/path\n"
            "To create file: touch /full/path/filename\n"
            "To list: ls -la /full/path\n"
            "To find: find /path -name 'pattern' -maxdepth 4\n"
            "To check disk space: df -h /Users\n"
            "To quit app: osascript -e 'tell app \"Name\" to quit'\n"
            "To move: mv /src /dst\n"
            "To copy: cp -r /src /dst\n"
            "To rename: mv /old /new\n"
            "To zip: zip -r /dst.zip /src\n"
            "For git: cd /path && git command\n"
            "For brew: /opt/homebrew/bin/brew command\n"
            "ONE line only. Nothing else."
        ),
        user=natural,
        temperature=0.05,
        stop=["\n", "Note:", "This"],
        timeout=25,
    )
    cmd = re.sub(r"^```[a-z]*\n?", "", cmd).strip("`").strip()
    return cmd.splitlines()[0].strip() if cmd else ""


def _run_cmd(cmd: str, timeout: int = 30) -> tuple:
    try:
        r = subprocess.run(
            cmd, shell=True, executable="/bin/zsh",
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def _spoken_result(cmd: str, rc: int, out: str, err: str) -> str:
    if rc != 0 and not out:
        return f"That failed: {(err or 'unknown error')[:150]}"
    if rc == 0 and not out:
        return "Done."
    if out and len(out) < 120 and "\n" not in out:
        return out
    snippet = out[:600]
    summary = _chat(
        system="Summarize this terminal output in 1-2 plain spoken sentences. No markdown.",
        user=f"Command: {cmd}\nOutput:\n{snippet}",
        temperature=0.2,
    )
    return summary or f"Done. {len(out.splitlines())} lines of output."


def handle_shell(query: str) -> str:
    """Natural language → zsh → safety check → confirm if destructive → run → speak result."""
    print(f"🐚 Shell: {query}")
    speak("On it.", wait=False)

    cmd = _generate_shell_cmd(query)
    if not cmd:
        return "I couldn't figure out the right command for that."
    print(f"🔧 Generated: {cmd}")

    ok, reason = _safe_check(cmd)
    if not ok:
        print(f"🚫 Blocked ({reason}): {cmd!r}")
        return "I can't do that — it would touch protected system files."

    if _DESTRUCTIVE_RE.search(cmd):
        short = cmd if len(cmd) <= 90 else cmd[:87] + "…"
        speak(f"This will run: {short}. Say yes to confirm or no to cancel.", wait=True)
        time.sleep(0.15)
        confirmation = _global_mic.listen() if _global_mic else ""
        if not re.search(r'\byes\b', confirmation.lower()):
            return "Cancelled."
        print("✅ Confirmed.")

    print(f"▶  Running: {cmd}")
    rc, out, err = _run_cmd(cmd)
    print(f"   exit={rc} out={out[:80]!r} err={err[:60]!r}")
    return _spoken_result(cmd, rc, out, err)


# ─────────────────────────────────────────────
# INTENT CLASSIFIER
# LLM-based: any phrasing maps correctly.
# "can you please create a new folder" → SHELL
# "hey open chrome for me" → OPEN
# No regex misses, no hallucinated actions.
# ─────────────────────────────────────────────
_INTENT_SYSTEM = """Classify the user voice command into exactly ONE category.
Reply with only the category name. Nothing else. No punctuation.

OPEN      - open, launch, or start an application
MUSIC     - control Spotify: play, pause, skip, volume, shuffle
WORK_MODE - activate work mode or dev environment
SYSTEM    - sleep, lock, shutdown, restart, reboot the computer
SHELL     - any file/folder operation (create, delete, move, copy, rename, list, find),
            disk space, git, brew, pip, kill/quit a process, zip/compress, system stats
STOP      - stop talking / shut up / cancel / nevermind
QUESTION  - everything else: general knowledge, questions, conversation"""


def _classify(text: str) -> str:
    """Returns one of: OPEN MUSIC WORK_MODE SYSTEM SHELL STOP QUESTION"""
    if not _ollama_alive():
        # Offline fallback — fast keyword match
        q = text.lower()
        if re.search(r'\b(stop|shut up|quiet|cancel|never ?mind)\b', q): return "STOP"
        if re.search(r'\b(open|launch|start)\b', q):                      return "OPEN"
        if re.search(r'\b(play|pause|skip|next|previous|shuffle|spotify)\b', q): return "MUSIC"
        if re.search(r'\bwork\s*mode\b', q):                               return "WORK_MODE"
        if re.search(r'\b(sleep|lock|shutdown|restart|reboot)\b', q):     return "SYSTEM"
        if re.search(r'\b(create|delete|move|copy|rename|list|find|folder|file|disk|git|brew|pip|kill|zip)\b', q): return "SHELL"
        return "QUESTION"

    raw = _chat(
        system=_INTENT_SYSTEM,
        user=text,
        temperature=0.0,
        stop=["\n", " ", ".", ","],
        timeout=10,
    ).strip().upper()

    valid = {"OPEN", "MUSIC", "WORK_MODE", "SYSTEM", "SHELL", "STOP", "QUESTION"}
    first = raw.split()[0] if raw else "QUESTION"
    return first if first in valid else "QUESTION"


# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
def route(text: str) -> str:
    if not text.strip():
        return "I didn't catch that."
    intent = _classify(text)
    print(f"🧠 Intent: {intent}")

    if intent == "STOP":
        stop_speaking()
        return ""
    if intent == "OPEN":
        return handle_open(text)
    if intent == "MUSIC":
        return handle_music(text)
    if intent == "WORK_MODE":
        return handle_work_mode()
    if intent == "SYSTEM":
        return handle_system(text)
    if intent == "SHELL":
        return handle_shell(text)
    return ask_ai(text)




# ─────────────────────────────────────────────
# JARVIS CLASS
# ─────────────────────────────────────────────
class Jarvis:
    def __init__(self):
        self._busy                = threading.Lock()
        self._smart_mic           = None
        self._pressed: set        = set()
        self._last_trigger: float = 0.0
        self._init_mic()

    def _init_mic(self):
        global _global_mic
        try:
            self._smart_mic = SmartMic()
            _global_mic = self._smart_mic
            print("✅ Smart mic ready (WebRTC VAD)")
        except Exception as e:
            print(f"⚠️  Mic init error: {e}")
            print("   Grant mic access: System Settings → Privacy → Microphone")

    # ── Hotkey (pynput Listener — avoids Python 3.14 GlobalHotKeys crash) ──
    def _on_press(self, key):
        self._pressed.add(key)
        has_cmd   = any(k in self._pressed for k in
                        (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r))
        has_shift = any(k in self._pressed for k in
                        (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r))
        has_j     = (isinstance(key, keyboard.KeyCode)
                     and key.char is not None
                     and key.char.lower() == 'j')
        if has_cmd and has_shift and has_j:
            now = time.monotonic()
            if now - self._last_trigger > 1.5:
                self._last_trigger = now
                self.activate()

    def _on_release(self, key):
        self._pressed.discard(key)

    def activate(self):
        if not self._busy.acquire(blocking=False):
            stop_speaking()
            print("⏳ Interrupted — press again to speak.")
            return

        def _run():
            try:
                stop_speaking()
                speak("Listening.", wait=True)  # finish speaking BEFORE mic opens
                time.sleep(0.15)                # let reverb die
                if not self._smart_mic:
                    speak("Microphone unavailable.")
                    return
                text = self._smart_mic.listen()
                if text:
                    response = route(text)
                    if response:
                        speak(response)
            finally:
                self._busy.release()
                print("🔇 Ready.\n")

        threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    if platform.system() != "Darwin":
        print("⚠️  Built for macOS — some features may not work on other systems.")

    print("=" * 52)
    print("  J.A.R.V.I.S.  —  Voice Assistant")
    print("=" * 52)
    print(f"  Model  : {MODEL} (Ollama)")
    print("  Hotkey : Command + Shift + J")
    print("  Quit   : Ctrl + C")
    print("=" * 52)

    _start_ollama()

    jarvis = Jarvis()

    try:
        # Use Listener directly — GlobalHotKeys has a broken _on_press
        # signature on Python 3.14 / newer pynput builds.
        listener = keyboard.Listener(
            on_press=jarvis._on_press,
            on_release=jarvis._on_release
        )
        listener.start()
        print("✅ Hotkey registered: Command + Shift + J")
        print("   Press it and speak any command or question.")
        print("   (If nothing happens, add Terminal to Accessibility in System Settings)\n")
        speak("Jarvis online. Press Command Shift J and speak.")
    except Exception as e:
        print(f"❌ Hotkey registration failed: {e}")
        print("   Fix: System Settings → Privacy & Security → Accessibility")
        print("        Add Terminal and re-run.")
        sys.exit(1)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n🛑 Jarvis shutting down.")
        speak("Going offline.")
        sys.exit(0)


if __name__ == "__main__":
    main()

