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
import json
import uuid
import queue
import resource
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

try:
    import numpy as np
except Exception:
    np = None

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OLLAMA_URL        = "http://localhost:11434"
MODEL             = "llama3.1:8b"
HOME              = os.path.expanduser("~")
LISTEN_CUE_MODE   = os.getenv("JARVIS_LISTEN_CUE", "beep").strip().lower()
STT_BACKEND       = os.getenv("JARVIS_STT_BACKEND", "auto").strip().lower()  # auto|local|google
LOCAL_STT_MODEL   = os.getenv("JARVIS_LOCAL_STT_MODEL", "tiny.en").strip()
LOCAL_STT_COMPUTE = os.getenv("JARVIS_LOCAL_STT_COMPUTE", "int8").strip()

# ── SmartMic constants ────────────────────────────────────────────────────────
VAD_SAMPLE_RATE      = 16000   # Hz  — required by webrtcvad
VAD_FRAME_MS         = 30      # ms per frame  (10 / 20 / 30 only)
VAD_FRAME_SAMPLES    = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)   # 480 samples
VAD_AGGRESSIVENESS   = 2       # 0=lenient … 3=aggressive non-speech filter
PRE_ROLL_FRAMES      = 10      # ~300ms buffered before speech start (catches first syllable)
SILENCE_END_FRAMES   = max(6, int(int(os.getenv("JARVIS_SILENCE_END_MS", "360")) / VAD_FRAME_MS))
MIN_SPEECH_FRAMES    = 3       # ignore clicks / pops shorter than this
MAX_RECORD_SECONDS   = 30      # safety ceiling
STARTUP_TIMEOUT_S    = 8       # give up if no speech within this time
LOCAL_STT_PARTIAL_MIN_MS = int(os.getenv("JARVIS_LOCAL_PARTIAL_MIN_MS", "800"))
LOCAL_STT_PARTIAL_INTERVAL_MS = int(os.getenv("JARVIS_LOCAL_PARTIAL_INTERVAL_MS", "450"))


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
        _start_ollama()
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
            "NEVER claim you are monitoring systems, watching services, or running in the background. "
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


def _play_listen_cue():
    if LISTEN_CUE_MODE == "none":
        return
    if LISTEN_CUE_MODE == "speech":
        speak("Listening.", wait=True)
        return
    # default: short system beep for minimal activation latency.
    subprocess.run(["osascript", "-e", "beep 1"], capture_output=True)


# ─────────────────────────────────────────────
# SMART MIC  — WebRTC VAD-based listener
# ─────────────────────────────────────────────
class SmartMic:
    def __init__(self):
        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self._pa  = pyaudio.PyAudio()
        self._rec = sr.Recognizer()
        self._local_model = None
        self._local_enabled = False
        self._partial_min_frames = max(8, int(LOCAL_STT_PARTIAL_MIN_MS / VAD_FRAME_MS))
        self._partial_interval_frames = max(6, int(LOCAL_STT_PARTIAL_INTERVAL_MS / VAD_FRAME_MS))
        self._init_stt_backend()

    def _init_stt_backend(self):
        wants_local = STT_BACKEND in {"auto", "local"}
        if not wants_local:
            print("🧠 STT backend: google")
            return
        if WhisperModel is None or np is None:
            if STT_BACKEND == "local":
                print("⚠️  Local STT requested but dependencies are missing. Falling back to Google STT.")
            return
        try:
            self._local_model = WhisperModel(LOCAL_STT_MODEL, compute_type=LOCAL_STT_COMPUTE)
            self._local_enabled = True
            print(f"🧠 STT backend: local ({LOCAL_STT_MODEL}, {LOCAL_STT_COMPUTE})")
        except Exception as exc:
            if STT_BACKEND == "local":
                print(f"⚠️  Local STT model failed to load: {exc}. Falling back to Google STT.")

    def _decode_local(self, raw: bytes, partial: bool = False) -> str:
        if not self._local_enabled or self._local_model is None or not raw or np is None:
            return ""
        try:
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._local_model.transcribe(
                pcm,
                language="en",
                beam_size=1,
                best_of=1,
                without_timestamps=True,
                condition_on_previous_text=not partial,
                vad_filter=False,
                temperature=0.0,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
            return text
        except Exception as exc:
            if not partial:
                print(f"⚠️  Local STT error: {exc}")
            return ""

    def _decode_google(self, raw: bytes) -> str:
        audio = sr.AudioData(raw, VAD_SAMPLE_RATE, 2)
        try:
            return self._rec.recognize_google(audio, language="en-US").strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            speak("Speech service unavailable.")
            return ""
        except Exception as exc:
            print(f"⚠️  STT error: {exc}")
            return ""

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
        speech_frames = 0
        last_partial_text = ""
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
                        speech_frames = len(pre_roll)
                        silence_ct = 0
                        print("🗨  Capturing speech…")
                    elif total > wait_frames:          # no speech in time
                        break
                else:
                    speech_buf.append(frame)
                    speech_frames += 1
                    if not is_speech:
                        silence_ct += 1
                        if silence_ct >= SILENCE_END_FRAMES:
                            print("⏹  End of speech.")
                            break
                    else:
                        silence_ct = 0

                    if (
                        self._local_enabled
                        and speech_frames >= self._partial_min_frames
                        and speech_frames % self._partial_interval_frames == 0
                    ):
                        partial = self._decode_local(b"".join(speech_buf), partial=True)
                        if partial and partial != last_partial_text:
                            last_partial_text = partial
                            print(f'📝 Partial: "{partial}"')
        finally:
            stream.stop_stream()
            stream.close()

        if not triggered or len(speech_buf) < MIN_SPEECH_FRAMES:
            return ""

        raw = b"".join(speech_buf)
        print("🔄 Recognising…")

        # Prefer local low-latency STT if available.
        if self._local_enabled:
            text = self._decode_local(raw, partial=False)
            print(f'📝 You said: "{text}"')
            if text:
                return text

        text = self._decode_google(raw)
        if text:
            print(f'📝 You said: "{text}"')
        return text


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

ACTION_CREATE_FOLDER = "create_folder"
ACTION_CREATE_FILE = "create_file"
ACTION_LIST_PATH = "list_path"
ACTION_FIND_NAME = "find_name"
ACTION_MOVE_PATH = "move_path"
ACTION_COPY_PATH = "copy_path"
ACTION_RENAME_PATH = "rename_path"
ACTION_DELETE_PATH = "delete_path"
ACTION_DISK_USAGE = "disk_usage"
ACTION_GIT_STATUS = "git_status"
ACTION_BATTERY_STATUS = "battery_status"

SUPPORTED_ACTIONS = {
    ACTION_CREATE_FOLDER,
    ACTION_CREATE_FILE,
    ACTION_LIST_PATH,
    ACTION_FIND_NAME,
    ACTION_MOVE_PATH,
    ACTION_COPY_PATH,
    ACTION_RENAME_PATH,
    ACTION_DELETE_PATH,
    ACTION_DISK_USAGE,
    ACTION_GIT_STATUS,
    ACTION_BATTERY_STATUS,
}

WRITE_ACTIONS = {
    ACTION_CREATE_FOLDER,
    ACTION_CREATE_FILE,
    ACTION_MOVE_PATH,
    ACTION_COPY_PATH,
    ACTION_RENAME_PATH,
    ACTION_DELETE_PATH,
}

DESTRUCTIVE_ACTIONS = {ACTION_DELETE_PATH}

PROTECTED_PATHS = [
    "/System", "/bin", "/sbin", "/usr", "/private/etc", "/Library/Apple", "/dev"
]

ACTION_TIMEOUT_SECONDS = 20
ACTION_MAX_RETRIES = 2
RATE_LIMIT_PER_MINUTE = 20
ALERT_FAILURE_THRESHOLD = 5

AUDIT_DIR = Path(HOME) / ".jarvis_audit"
AUDIT_FILE = AUDIT_DIR / "audit.jsonl"
METRICS_FILE = AUDIT_DIR / "metrics.jsonl"


@dataclass
class ActionRequest:
    action: str
    args: dict[str, Any]
    principal: str
    reason: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_approval: bool = False


@dataclass
class ActionResult:
    ok: bool
    return_code: int
    stdout: str
    stderr: str
    duration_ms: int
    command_repr: str


@dataclass
class ActionJob:
    request: ActionRequest
    done: threading.Event = field(default_factory=threading.Event)
    result: ActionResult | None = None


@dataclass
class MissionPlan:
    mission_id: str
    requests: list[ActionRequest]
    created_at: float = field(default_factory=time.time)


class FixedWindowRateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, int]] = {}

    def allow(self, principal: str) -> tuple[bool, int]:
        now_min = int(time.time() // 60)
        with self._lock:
            minute, count = self._state.get(principal, (now_min, 0))
            if minute != now_min:
                minute, count = now_min, 0
            if count >= self.max_per_minute:
                retry_after = 60 - int(time.time() % 60)
                return False, max(retry_after, 1)
            self._state[principal] = (minute, count + 1)
        return True, 0


_rate_limiter = FixedWindowRateLimiter(RATE_LIMIT_PER_MINUTE)
_action_queue: queue.Queue[ActionJob] = queue.Queue(maxsize=128)
_queue_worker_started = False
_queue_lock = threading.Lock()
_failure_streak = 0
_pending_mission: MissionPlan | None = None
_pending_mission_lock = threading.Lock()
_last_mission_report = "No mission has run yet."


def _ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]):
    _ensure_audit_dir()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _audit(event: str, request: ActionRequest, decision: PolicyDecision | None = None,
           result: ActionResult | None = None, message: str = ""):
    payload: dict[str, Any] = {
        "ts": time.time(),
        "event": event,
        "request_id": request.request_id,
        "principal": request.principal,
        "action": request.action,
        "args": request.args,
        "message": message,
    }
    if decision:
        payload["policy"] = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "requires_approval": decision.requires_approval,
        }
    if result:
        payload["result"] = {
            "ok": result.ok,
            "return_code": result.return_code,
            "duration_ms": result.duration_ms,
            "command": result.command_repr,
            "stderr": result.stderr[:300],
        }
    _append_jsonl(AUDIT_FILE, payload)


def _metric(name: str, value: float, tags: dict[str, str] | None = None):
    _append_jsonl(METRICS_FILE, {
        "ts": time.time(),
        "name": name,
        "value": value,
        "tags": tags or {},
    })


def _local_alert(message: str):
    print(f"🚨 ALERT: {message}")
    _metric("alert", 1, {"message": message[:80]})


def _principal() -> str:
    return os.getenv("USER", "local_hotkey_user")


def _normalize_path(raw: str) -> str:
    cleaned = raw.strip().strip("'\"").rstrip(".?!")
    if cleaned.startswith("~"):
        cleaned = os.path.expanduser(cleaned)
    elif not cleaned.startswith("/"):
        cleaned = os.path.join(HOME, cleaned)
    return str(Path(cleaned).expanduser().resolve())


def _is_protected(path: str) -> bool:
    resolved = str(Path(path).resolve())
    return any(resolved == p or resolved.startswith(p + "/") for p in PROTECTED_PATHS)


def _is_under_home(path: str) -> bool:
    resolved = str(Path(path).resolve())
    home_resolved = str(Path(HOME).resolve())
    return resolved == home_resolved or resolved.startswith(home_resolved + "/")


def _build_action_request(query: str) -> ActionRequest | None:
    text = query.strip()
    lower = text.lower()
    principal = _principal()

    if re.search(r'\b(disk\s+space|storage|disk\s+usage)\b', lower):
        return ActionRequest(action=ACTION_DISK_USAGE, args={}, principal=principal, reason=text)

    if re.search(r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count)\b', lower):
        return ActionRequest(action=ACTION_BATTERY_STATUS, args={}, principal=principal, reason=text)

    match = re.search(r'\bgit\s+status(?:\s+in\s+(.+))?$', lower)
    if match:
        repo = _normalize_path(match.group(1) or os.getcwd())
        return ActionRequest(action=ACTION_GIT_STATUS, args={"repo": repo}, principal=principal, reason=text)

    match = re.search(r'\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:called\s+)?(.+)$', lower)
    if match:
        return ActionRequest(action=ACTION_CREATE_FOLDER, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

    match = re.search(r'\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?file\s+(?:called\s+)?(.+)$', lower)
    if match:
        return ActionRequest(action=ACTION_CREATE_FILE, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

    match = re.search(r'\b(?:list|show)\s+(?:files\s+)?(?:in|at)?\s*(.+)$', lower)
    if match and match.group(1):
        return ActionRequest(action=ACTION_LIST_PATH, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

    match = re.search(r'\bfind\s+(.+?)\s+in\s+(.+)$', lower)
    if match:
        return ActionRequest(
            action=ACTION_FIND_NAME,
            args={"pattern": match.group(1).strip().strip("'\""), "path": _normalize_path(match.group(2))},
            principal=principal,
            reason=text,
        )

    match = re.search(r'\bmove\s+(.+?)\s+to\s+(.+)$', lower)
    if match:
        return ActionRequest(
            action=ACTION_MOVE_PATH,
            args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))},
            principal=principal,
            reason=text,
        )

    match = re.search(r'\bcopy\s+(.+?)\s+to\s+(.+)$', lower)
    if match:
        return ActionRequest(
            action=ACTION_COPY_PATH,
            args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))},
            principal=principal,
            reason=text,
        )

    match = re.search(r'\brename\s+(.+?)\s+to\s+(.+)$', lower)
    if match:
        return ActionRequest(
            action=ACTION_RENAME_PATH,
            args={"src": _normalize_path(match.group(1)), "dst": _normalize_path(match.group(2))},
            principal=principal,
            reason=text,
        )

    match = re.search(r'\b(?:delete|remove)\s+(.+)$', lower)
    if match:
        return ActionRequest(action=ACTION_DELETE_PATH, args={"path": _normalize_path(match.group(1))}, principal=principal, reason=text)

    return None


def _shorten(text: str, limit: int = 64) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _describe_action_request(request: ActionRequest) -> str:
    action = request.action
    args = request.args
    if action == ACTION_CREATE_FOLDER:
        return f"create folder {_shorten(args.get('path', ''))}"
    if action == ACTION_CREATE_FILE:
        return f"create file {_shorten(args.get('path', ''))}"
    if action == ACTION_LIST_PATH:
        return f"list {_shorten(args.get('path', ''))}"
    if action == ACTION_FIND_NAME:
        pattern = args.get("pattern", "")
        return f"find {pattern} in {_shorten(args.get('path', ''))}"
    if action == ACTION_MOVE_PATH:
        return f"move {_shorten(args.get('src', ''))} to {_shorten(args.get('dst', ''))}"
    if action == ACTION_COPY_PATH:
        return f"copy {_shorten(args.get('src', ''))} to {_shorten(args.get('dst', ''))}"
    if action == ACTION_RENAME_PATH:
        return f"rename {_shorten(args.get('src', ''))} to {_shorten(args.get('dst', ''))}"
    if action == ACTION_DELETE_PATH:
        return f"delete {_shorten(args.get('path', ''))}"
    if action == ACTION_DISK_USAGE:
        return "check disk usage"
    if action == ACTION_BATTERY_STATUS:
        return "check battery status and health"
    if action == ACTION_GIT_STATUS:
        return f"git status in {_shorten(args.get('repo', ''))}"
    return action


def _split_mission_query(query: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", query.strip())
    if not normalized:
        return []
    parts = re.split(r"\s*(?:,?\s+and\s+then\s+|,?\s+then\s+|;\s*|->)\s*", normalized, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def _build_mission_plan(query: str) -> MissionPlan | None:
    parts = _split_mission_query(query)
    if len(parts) < 2:
        return None

    requests: list[ActionRequest] = []
    for idx, part in enumerate(parts, start=1):
        request = _build_action_request(part)
        if not request:
            return None
        request.reason = f"{query.strip()} [step {idx}]"
        requests.append(request)

    return MissionPlan(mission_id=str(uuid.uuid4()), requests=requests)


def _peek_pending_mission() -> MissionPlan | None:
    with _pending_mission_lock:
        return _pending_mission


def _set_pending_mission(plan: MissionPlan) -> None:
    global _pending_mission
    with _pending_mission_lock:
        _pending_mission = plan


def _clear_pending_mission() -> MissionPlan | None:
    global _pending_mission
    with _pending_mission_lock:
        plan = _pending_mission
        _pending_mission = None
    return plan


def _is_mission_execute_command(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"\b(yes|execute mission|run mission|run it|proceed|do it)\b", lower))


def _is_mission_cancel_command(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"\b(no|cancel mission|abort mission|stop mission)\b", lower))


def _policy_check(request: ActionRequest, *, consume_rate_limit: bool = True) -> PolicyDecision:
    if request.action not in SUPPORTED_ACTIONS:
        return PolicyDecision(False, "unsupported action")

    if consume_rate_limit:
        allowed, retry_after = _rate_limiter.allow(request.principal)
        if not allowed:
            return PolicyDecision(False, f"rate limit exceeded; retry in {retry_after}s")

    check_paths: list[str] = []
    for key in ("path", "src", "dst", "repo"):
        value = request.args.get(key)
        if isinstance(value, str):
            check_paths.append(value)

    for path in check_paths:
        if _is_protected(path):
            return PolicyDecision(False, f"protected path blocked: {path}")

    if request.action in WRITE_ACTIONS:
        for path in check_paths:
            if not _is_under_home(path):
                return PolicyDecision(False, f"write action outside home blocked: {path}")

    if request.action == ACTION_GIT_STATUS:
        repo = request.args.get("repo", "")
        if not _is_under_home(repo):
            return PolicyDecision(False, "git status outside home blocked")

    return PolicyDecision(True, "allowed", request.action in DESTRUCTIVE_ACTIONS)


def _apply_subprocess_limits():
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except Exception:
        pass


def _run_safe_process(args: list[str], timeout: int = ACTION_TIMEOUT_SECONDS) -> ActionResult:
    started = time.time()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_apply_subprocess_limits,
        )
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(
            ok=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            duration_ms=duration_ms,
            command_repr=" ".join(args),
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", f"Timed out after {timeout}s", duration_ms, " ".join(args))
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", str(exc), duration_ms, " ".join(args))


def _extract_battery_summary(pmset_output: str, profiler_output: str) -> str:
    parts: list[str] = []

    charge_match = re.search(r"(\d+)%", pmset_output)
    state_match = re.search(r";\s*([^;]+);", pmset_output)
    if charge_match:
        status = f"Battery is at {charge_match.group(1)} percent"
        if state_match:
            status += f", {state_match.group(1).strip()}"
        parts.append(status + ".")

    capacity_match = re.search(r"Maximum Capacity:\s*(\d+)%", profiler_output, flags=re.IGNORECASE)
    cycle_match = re.search(r"Cycle Count:\s*(\d+)", profiler_output, flags=re.IGNORECASE)
    condition_match = re.search(r"Condition:\s*([A-Za-z ]+)", profiler_output, flags=re.IGNORECASE)

    health_bits: list[str] = []
    if capacity_match:
        health_bits.append(f"maximum capacity {capacity_match.group(1)} percent")
    if cycle_match:
        health_bits.append(f"cycle count {cycle_match.group(1)}")
    if condition_match:
        health_bits.append(f"condition {condition_match.group(1).strip().lower()}")
    if health_bits:
        parts.append("Battery health: " + ", ".join(health_bits) + ".")

    return " ".join(parts).strip()


def _run_battery_status_action() -> ActionResult:
    started = time.time()
    batt = _run_safe_process(["pmset", "-g", "batt"], timeout=6)
    profiler = _run_safe_process(["system_profiler", "SPPowerDataType", "-detailLevel", "mini"], timeout=12)

    summary = _extract_battery_summary(batt.stdout, profiler.stdout)
    ok = batt.ok or profiler.ok
    if summary:
        return ActionResult(
            ok=ok,
            return_code=0 if ok else 1,
            stdout=summary,
            stderr=(batt.stderr + " " + profiler.stderr).strip(),
            duration_ms=int((time.time() - started) * 1000),
            command_repr="pmset -g batt && system_profiler SPPowerDataType -detailLevel mini",
        )

    stderr = (batt.stderr + " " + profiler.stderr).strip() or "Unable to read battery details."
    return ActionResult(
        ok=False,
        return_code=1,
        stdout="",
        stderr=stderr,
        duration_ms=int((time.time() - started) * 1000),
        command_repr="pmset -g batt && system_profiler SPPowerDataType -detailLevel mini",
    )


def _execute_action_request(request: ActionRequest) -> ActionResult:
    action = request.action
    args = request.args

    if action == ACTION_CREATE_FOLDER:
        return _run_safe_process(["mkdir", "-p", args["path"]])
    if action == ACTION_CREATE_FILE:
        return _run_safe_process(["touch", args["path"]])
    if action == ACTION_LIST_PATH:
        return _run_safe_process(["ls", "-la", args["path"]])
    if action == ACTION_FIND_NAME:
        return _run_safe_process(["find", args["path"], "-maxdepth", "4", "-name", args["pattern"]])
    if action in {ACTION_MOVE_PATH, ACTION_RENAME_PATH}:
        return _run_safe_process(["mv", args["src"], args["dst"]])
    if action == ACTION_COPY_PATH:
        return _run_safe_process(["cp", "-R", args["src"], args["dst"]])
    if action == ACTION_DELETE_PATH:
        script = f'tell app "Finder" to delete POSIX file "{args["path"]}"'
        return _run_safe_process(["osascript", "-e", script])
    if action == ACTION_DISK_USAGE:
        return _run_safe_process(["df", "-h", "/Users"])
    if action == ACTION_BATTERY_STATUS:
        return _run_battery_status_action()
    if action == ACTION_GIT_STATUS:
        return _run_safe_process(["git", "-C", args["repo"], "status", "--short"])

    return ActionResult(False, -1, "", f"Unsupported action: {action}", 0, action)


def _format_action_result(result: ActionResult) -> str:
    if not result.ok and not result.stdout:
        return f"That failed: {(result.stderr or 'unknown error')[:150]}"
    if result.ok and not result.stdout:
        return "Done."
    if result.stdout and len(result.stdout) < 120 and "\n" not in result.stdout:
        return result.stdout
    snippet = result.stdout[:600]
    summary = _chat(
        system="Summarize this command output in 1-2 plain spoken sentences. No markdown.",
        user=f"Command: {result.command_repr}\nOutput:\n{snippet}",
        temperature=0.2,
    )
    return summary or f"Done. {len(result.stdout.splitlines())} lines of output."


def _action_worker_loop():
    global _failure_streak
    while True:
        job = _action_queue.get()
        request = job.request
        result = ActionResult(False, -1, "", "unknown", 0, request.action)

        for attempt in range(ACTION_MAX_RETRIES + 1):
            result = _execute_action_request(request)
            _metric("action.duration_ms", result.duration_ms, {"action": request.action, "attempt": str(attempt)})
            if result.ok:
                break
            if "Timed out" in result.stderr and attempt < ACTION_MAX_RETRIES:
                time.sleep(0.2 * (2 ** attempt))
                continue
            break

        if result.ok:
            _failure_streak = 0
        else:
            _failure_streak += 1
            if _failure_streak >= ALERT_FAILURE_THRESHOLD:
                _local_alert("Consecutive action failures exceeded threshold")

        job.result = result
        _audit("action_executed", request, result=result)
        job.done.set()
        _action_queue.task_done()


def _ensure_action_worker():
    global _queue_worker_started
    with _queue_lock:
        if _queue_worker_started:
            return
        threading.Thread(target=_action_worker_loop, daemon=True).start()
        _queue_worker_started = True


def _dispatch_action_job(request: ActionRequest) -> tuple[bool, ActionResult | None, str]:
    try:
        job = ActionJob(request=request)
        _action_queue.put(job, timeout=2)
    except queue.Full:
        return False, None, "System is busy. Please try again in a few seconds."

    wait_timeout = ACTION_TIMEOUT_SECONDS * (ACTION_MAX_RETRIES + 1) + 3
    completed = job.done.wait(timeout=wait_timeout)
    if not completed or not job.result:
        _audit("action_timeout", request, message="queue wait timeout")
        return False, None, "The action timed out before completion."
    return True, job.result, ""


def _preview_mission(plan: MissionPlan) -> str:
    for idx, request in enumerate(plan.requests, start=1):
        decision = _policy_check(request, consume_rate_limit=False)
        if not decision.allowed:
            return f"Mission blocked at step {idx}: {decision.reason}."

    _set_pending_mission(plan)
    preview_parts = [_describe_action_request(request) for request in plan.requests[:4]]
    preview = "; ".join(preview_parts)
    if len(plan.requests) > 4:
        preview += f"; plus {len(plan.requests) - 4} more step(s)"

    destructive_steps = sum(1 for request in plan.requests if request.action in DESTRUCTIVE_ACTIONS)
    note = ""
    if destructive_steps:
        note = " Destructive steps will still require spoken approval."

    return (
        f"Mission ready with {len(plan.requests)} steps: {preview}. "
        "Say execute mission to run it, or cancel mission."
        + note
    )


def _execute_mission_plan(plan: MissionPlan) -> str:
    global _last_mission_report
    success_count = 0
    failure_count = 0
    report_lines: list[str] = []

    for idx, request in enumerate(plan.requests, start=1):
        decision = _policy_check(request)
        _audit("action_requested", request, decision=decision, message=f"mission_id={plan.mission_id};step={idx}")

        if not decision.allowed:
            failure_count += 1
            report_lines.append(f"Step {idx}: blocked ({decision.reason})")
            continue

        if decision.requires_approval and not _confirm_destructive_action(request):
            failure_count += 1
            _audit(
                "action_cancelled",
                request,
                decision=decision,
                message=f"mission_id={plan.mission_id};step={idx};destructive approval denied",
            )
            report_lines.append(f"Step {idx}: cancelled by approval gate")
            continue

        dispatched, result, dispatch_message = _dispatch_action_job(request)
        if not dispatched or not result:
            failure_count += 1
            report_lines.append(f"Step {idx}: failed ({dispatch_message})")
            continue

        if result.ok:
            success_count += 1
            report_lines.append(f"Step {idx}: ok ({_describe_action_request(request)})")
        else:
            failure_count += 1
            brief = (result.stderr or "unknown error")[:120]
            report_lines.append(f"Step {idx}: failed ({brief})")

    _append_jsonl(
        AUDIT_FILE,
        {
            "ts": time.time(),
            "event": "mission_executed",
            "mission_id": plan.mission_id,
            "steps_total": len(plan.requests),
            "steps_ok": success_count,
            "steps_failed": failure_count,
        },
    )

    _last_mission_report = "Mission report. " + " ".join(report_lines[:8])

    if failure_count == 0:
        return f"Mission complete. All {success_count} steps succeeded."
    return (
        f"Mission complete with issues. {success_count} succeeded and {failure_count} failed. "
        "Say mission report for step details."
    )


def _handle_pending_mission_control(query: str) -> str | None:
    plan = _peek_pending_mission()
    if not plan:
        return None

    lower = query.lower().strip()
    if _is_mission_cancel_command(lower):
        _clear_pending_mission()
        return "Mission cancelled."

    if _is_mission_execute_command(lower):
        to_run = _clear_pending_mission()
        if not to_run:
            return "No pending mission."
        return _execute_mission_plan(to_run)

    if re.search(r"\bmission status\b", lower):
        return f"A mission with {len(plan.requests)} steps is pending. Say execute mission or cancel mission."

    if re.search(r"\bmission report\b", lower):
        return _last_mission_report

    return None


def _confirm_destructive_action(request: ActionRequest) -> bool:
    path = request.args.get("path", "")
    label = path if len(path) <= 80 else path[:77] + "..."
    speak(f"This will delete {label}. Say yes to confirm or no to cancel.", wait=True)
    time.sleep(0.15)
    confirmation = _global_mic.listen() if _global_mic else ""
    return bool(re.search(r'\byes\b', confirmation.lower()))


def handle_shell(query: str) -> str:
    """Typed action execution path with policy checks, queueing, retries, audit, and approval gates."""
    _ensure_action_worker()
    pending_control = _handle_pending_mission_control(query)
    if pending_control is not None:
        return pending_control

    if re.search(r"\bmission report\b", query.lower()):
        return _last_mission_report

    mission_plan = _build_mission_plan(query)
    if mission_plan:
        return _preview_mission(mission_plan)

    request = _build_action_request(query)
    if not request:
        return "I can run structured actions like create, list, find, move, copy, delete, disk usage, battery status, or git status."

    decision = _policy_check(request)
    _audit("action_requested", request, decision=decision)

    if not decision.allowed:
        return f"Blocked by policy: {decision.reason}."

    if decision.requires_approval and not _confirm_destructive_action(request):
        _audit("action_cancelled", request, decision=decision, message="destructive approval denied")
        return "Cancelled."

    dispatched, result, dispatch_message = _dispatch_action_job(request)
    if not dispatched or not result:
        return dispatch_message
    return _format_action_result(result)


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
IMPORTANT - Only classify as MUSIC when the user clearly asks to control Spotify/music playback.
QUESTION  - everything else: general knowledge, questions, conversation"""


def _classify_by_rules(text: str) -> str | None:
    q = text.lower().strip()
    if not q:
        return "QUESTION"

    if re.search(r'\b(stop|shut up|quiet|cancel|never ?mind)\b', q):
        return "STOP"
    if re.search(r'\bwork\s*mode\b', q):
        return "WORK_MODE"
    if re.search(r'\b(sleep|lock|shutdown|restart|reboot)\b', q):
        return "SYSTEM"
    if re.search(r'\b(open|launch|start)\b', q):
        return "OPEN"

    music_command = re.search(r'\b(play|pause|skip|next|previous|shuffle|volume)\b', q)
    music_target = re.search(r'\b(spotify|music|song|track|playlist)\b', q)
    if music_target and music_command:
        return "MUSIC"
    if re.match(r'^\s*(play|pause|skip|next|previous|shuffle)\b', q):
        return "MUSIC"

    shell_markers = [
        r'\b(create|make)\b',
        r'\b(delete|remove)\b',
        r'\b(move|copy|rename)\b',
        r'\b(list|show)\s+(files|folders|directory|dir|in|at)\b',
        r'\bfind\b',
        r'\b(folder|directory|file)\b',
        r'\b(disk\s+space|storage|disk\s+usage)\b',
        r'\bgit\s+status\b',
        r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count)\b',
    ]
    for pattern in shell_markers:
        if re.search(pattern, q):
            return "SHELL"

    if re.match(r"^\s*(what|what's|whats|who|where|when|why|how|is|are|can|could|would|do)\b", q):
        return "QUESTION"

    return None


def _classify(text: str) -> str:
    """Returns one of: OPEN MUSIC WORK_MODE SYSTEM SHELL STOP QUESTION"""
    rule_match = _classify_by_rules(text)
    if rule_match is not None:
        return rule_match

    if not _ollama_alive():
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
    pending_control = _handle_pending_mission_control(text)
    if pending_control is not None:
        return pending_control

    # Route structured actions directly to the shell handler to avoid intent
    # misclassification for command-like phrasing.
    if _build_mission_plan(text) is not None or _build_action_request(text) is not None:
        return handle_shell(text)

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
                _play_listen_cue()
                time.sleep(0.05)
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
    print("  Shell  : ENABLED (typed safe actions only)")
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
