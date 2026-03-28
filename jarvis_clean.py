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
import shutil
import select
import difflib
import datetime
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

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OLLAMA_URL        = "http://localhost:11434"
MODEL             = "llama3.1:8b"
HOME              = os.path.expanduser("~")
LISTEN_CUE_MODE   = os.getenv("JARVIS_LISTEN_CUE", "beep").strip().lower()
STT_BACKEND       = os.getenv("JARVIS_STT_BACKEND", "apple_native").strip().lower()  # auto|apple_native|local|google
LOCAL_STT_MODEL   = os.getenv("JARVIS_LOCAL_STT_MODEL", "tiny.en").strip()
LOCAL_STT_COMPUTE = os.getenv("JARVIS_LOCAL_STT_COMPUTE", "int8").strip()
TRIGGER_MODE      = os.getenv("JARVIS_TRIGGER_MODE", "hotkey").strip().lower()  # hotkey|wake|hybrid
VAD_PROFILE       = os.getenv("JARVIS_VAD_PROFILE", "fast").strip().lower()  # fast|balanced|robust
WAKEWORD_BACKEND  = os.getenv("JARVIS_WAKEWORD_BACKEND", "openwakeword").strip().lower()
TRANSLATION_BACKEND = os.getenv("JARVIS_TRANSLATION_BACKEND", "local").strip().lower()
TRANSLATION_DEFAULT_TARGET = os.getenv("JARVIS_TRANSLATION_DEFAULT_TARGET", "spanish").strip().lower()
RESPONSE_STYLE    = os.getenv("JARVIS_RESPONSE_STYLE", "truth_concise").strip().lower()  # truth_concise|balanced
CLASSIFIER_MODE   = os.getenv("JARVIS_CLASSIFIER_MODE", "rules").strip().lower()  # rules|llm
WAKEWORD_MIN_INTERVAL_MS = int(os.getenv("JARVIS_WAKEWORD_MIN_INTERVAL_MS", "1200"))
WAKEWORD_TTS_GUARD_MS = int(os.getenv("JARVIS_WAKEWORD_TTS_GUARD_MS", "1800"))
WAKEWORD_MAX_WORDS = int(os.getenv("JARVIS_WAKEWORD_MAX_WORDS", "4"))
WAKEWORD_THRESHOLD = float(os.getenv("JARVIS_WAKEWORD_THRESHOLD", "0.55"))
WAKEWORD_POLL_SECONDS = float(os.getenv("JARVIS_WAKEWORD_POLL_SECONDS", "0.8"))
APPLE_STT_LANGUAGE = os.getenv("JARVIS_APPLE_STT_LANGUAGE", "en-US").strip()
APPLE_STT_TIMEOUT_PADDING_S = int(os.getenv("JARVIS_APPLE_STT_TIMEOUT_PADDING_S", "4"))
APPLE_STT_SILENCE_END_MS = int(os.getenv("JARVIS_APPLE_STT_SILENCE_END_MS", "420"))
APPLE_STT_MIN_SPEECH_MS = int(os.getenv("JARVIS_APPLE_STT_MIN_SPEECH_MS", "170"))
APPLE_STT_ENERGY_FLOOR = float(os.getenv("JARVIS_APPLE_STT_ENERGY_FLOOR", "0.010"))
APPLE_STT_ENERGY_MULTIPLIER = float(os.getenv("JARVIS_APPLE_STT_ENERGY_MULTIPLIER", "2.0"))
APPLE_STT_BUNDLE_ID = os.getenv("JARVIS_APPLE_STT_BUNDLE_ID", "com.jarvis.speechhelper").strip()
APPLE_STT_FORCE_HELPER = os.getenv("JARVIS_FORCE_APPLE_HELPER", "0").strip() == "1"
SHOW_TURN_TIMERS = os.getenv("JARVIS_SHOW_TURN_TIMERS", "1").strip() == "1"
SHOW_PARTIALS = os.getenv("JARVIS_SHOW_PARTIALS", "1").strip() == "1"
LOCAL_STT_PARTIAL_MAX_UPDATES = int(os.getenv("JARVIS_LOCAL_PARTIAL_MAX_UPDATES", "10"))
DEBUG_AUDIO_ENABLED = os.getenv("JARVIS_DEBUG_AUDIO", "0").strip() == "1"
DEBUG_AUDIO_DIR = Path(os.getenv("JARVIS_DEBUG_AUDIO_DIR", str(Path(HOME) / ".jarvis_debug" / "audio"))).expanduser()

# ── SmartMic constants ────────────────────────────────────────────────────────
VAD_SAMPLE_RATE      = 16000   # Hz  — required by webrtcvad
VAD_FRAME_MS         = 30      # ms per frame  (10 / 20 / 30 only)
VAD_FRAME_SAMPLES    = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)   # 480 samples
PRE_ROLL_FRAMES      = 10      # ~300ms buffered before speech start (catches first syllable)
MIN_SPEECH_FRAMES    = 3       # ignore clicks / pops shorter than this
MAX_RECORD_SECONDS   = 30      # safety ceiling
STARTUP_TIMEOUT_S    = 8       # give up if no speech within this time
LOCAL_STT_PARTIAL_MIN_MS = int(os.getenv("JARVIS_LOCAL_PARTIAL_MIN_MS", "800"))
LOCAL_STT_PARTIAL_INTERVAL_MS = int(os.getenv("JARVIS_LOCAL_PARTIAL_INTERVAL_MS", "450"))
LOCAL_STT_BEAM_SIZE = int(os.getenv("JARVIS_LOCAL_STT_BEAM_SIZE", "3"))
LOCAL_STT_BEST_OF = int(os.getenv("JARVIS_LOCAL_STT_BEST_OF", "3"))
LOCAL_STT_CONDITION_ON_PREVIOUS = os.getenv("JARVIS_LOCAL_STT_CONDITION_ON_PREVIOUS", "0").strip() == "1"
LOCAL_STT_INITIAL_PROMPT = os.getenv(
    "JARVIS_LOCAL_STT_INITIAL_PROMPT",
    "jarvis battery health wifi internet volume now playing spotify active app",
).strip()

_VAD_PROFILE_PRESETS = {
    "fast": {"aggressiveness": 2, "silence_end_ms": 280},
    "balanced": {"aggressiveness": 2, "silence_end_ms": 420},
    "robust": {"aggressiveness": 3, "silence_end_ms": 620},
}
_vad_profile = _VAD_PROFILE_PRESETS.get(VAD_PROFILE, _VAD_PROFILE_PRESETS["fast"])
VAD_AGGRESSIVENESS = int(os.getenv("JARVIS_VAD_AGGRESSIVENESS", str(_vad_profile["aggressiveness"])))
_silence_end_ms = int(os.getenv("JARVIS_SILENCE_END_MS", str(_vad_profile["silence_end_ms"])))
SILENCE_END_FRAMES = max(6, int(_silence_end_ms / VAD_FRAME_MS))


# ─────────────────────────────────────────────
# TTS  — macOS `say`, interruptible
# ─────────────────────────────────────────────
_say_proc: subprocess.Popen | None = None
_last_tts_started_monotonic: float = 0.0

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
    global _last_tts_started_monotonic
    stop_speaking()
    print(f"🗣  Jarvis: {text}")
    _last_tts_started_monotonic = time.monotonic()
    _say_proc = subprocess.Popen(["say", "-r", "185", text])
    if wait:
        _say_proc.wait()


def _recent_tts_activity(within_ms: int) -> bool:
    if _last_tts_started_monotonic <= 0:
        return False
    return ((time.monotonic() - _last_tts_started_monotonic) * 1000.0) <= float(within_ms)


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


TRUTH_CONCISE_SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., a voice assistant. "
    "Answer in plain spoken English, maximum 1 sentence, no markdown. "
    "Be factual and concise. "
    "If unsure, say you cannot verify it. "
    "CRITICAL: You cannot perform actions on the computer yourself. "
    "NEVER claim you created, opened, deleted, monitored, or performed actions. "
    "NEVER invent live system state."
)

BALANCED_SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., a voice assistant. "
    "Answer in plain spoken English, maximum 3 sentences, no markdown. "
    "CRITICAL: You cannot perform actions on the computer yourself. "
    "Only the Python code beneath you can open apps, create files, run commands, etc. "
    "If asked to do something on the computer, say you will pass it to the system. "
    "NEVER claim you created, opened, deleted, or performed any action. "
    "NEVER claim you are monitoring systems, watching services, or running in the background. "
    "NEVER write 'User:', 'Human:', or simulate a dialogue."
)

SUMMARY_SYSTEM_PROMPT = (
    "Summarize this command output in 1-2 plain spoken sentences. No markdown."
)


def ask_ai(prompt: str) -> str:
    """General Q&A. Strictly forbidden from pretending to perform computer actions."""
    if not _ollama_alive():
        _start_ollama()
        if not _ollama_alive():
            return "The AI is offline. Make sure Ollama is running."
    if RESPONSE_STYLE == "truth_concise":
        system_prompt = TRUTH_CONCISE_SYSTEM_PROMPT
        temperature = 0.1
    else:
        system_prompt = BALANCED_SYSTEM_PROMPT
        temperature = 0.3

    return _chat(system=system_prompt, user=prompt, temperature=temperature)


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
        self._stt_mode = "google"
        self._apple_native_enabled = False
        self._apple_stt_binary: str | None = None
        self._apple_daemon_proc: subprocess.Popen | None = None
        self._apple_daemon_lock = threading.Lock()
        self._local_model = None
        self._local_enabled = False
        self._partial_min_frames = max(8, int(LOCAL_STT_PARTIAL_MIN_MS / VAD_FRAME_MS))
        self._partial_interval_frames = max(6, int(LOCAL_STT_PARTIAL_INTERVAL_MS / VAD_FRAME_MS))
        self.last_capture_info: dict[str, int] = {}
        self._init_stt_backend()

    def _debug_dump_audio(self, raw: bytes, sample_rate: int) -> None:
        if not DEBUG_AUDIO_ENABLED or not raw:
            return
        try:
            DEBUG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = DEBUG_AUDIO_DIR / f"turn-{ts}.wav"
            import wave

            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(raw)
            print(f"📁 Saved debug audio to {path}")
        except Exception as exc:
            print(f"⚠️  Failed to write debug audio: {exc}")

    def _ensure_apple_stt_binary(self) -> str | None:
        if platform.system() != "Darwin":
            return None
        if shutil.which("xcrun") is None:
            print("⚠️  xcrun not found. Apple native STT unavailable.")
            return None

        src = Path(__file__).resolve().parent / "scripts" / "apple_stt_once.swift"
        if not src.exists():
            print("⚠️  Apple STT source script is missing. Falling back to another STT backend.")
            return None

        # TCC on newer macOS requires usage descriptions in an Info.plist.
        # Build as an app bundle executable to avoid privacy-violation aborts.
        app_contents = Path(HOME) / ".jarvis_cache" / "apps" / "JarvisSpeechHelper.app" / "Contents"
        macos_dir = app_contents / "MacOS"
        resources_dir = app_contents / "Resources"
        plist_path = app_contents / "Info.plist"
        binary = macos_dir / "apple_stt_once"

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleExecutable</key><string>apple_stt_once</string>
  <key>CFBundleIdentifier</key><string>{APPLE_STT_BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>JarvisSpeechHelper</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Jarvis uses speech recognition to transcribe your voice commands.</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Jarvis uses your microphone to listen for voice commands.</string>
</dict>
</plist>
"""

        needs_build = (not binary.exists()) or (src.stat().st_mtime > binary.stat().st_mtime)
        needs_plist = (not plist_path.exists()) or (plist_path.read_text(encoding="utf-8", errors="ignore") != plist_content)
        if needs_build:
            macos_dir.mkdir(parents=True, exist_ok=True)
            resources_dir.mkdir(parents=True, exist_ok=True)
            compile_cmd = [
                "xcrun",
                "swiftc",
                "-O",
                str(src),
                "-framework",
                "Speech",
                "-framework",
                "AVFoundation",
                "-o",
                str(binary),
            ]
            build = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=45)
            if build.returncode != 0:
                print(f"⚠️  Apple STT build failed: {(build.stderr or build.stdout).strip()[:260]}")
                return None
        if needs_plist:
            plist_path.write_text(plist_content, encoding="utf-8")
        # ad-hoc signing keeps bundle runnable and more predictable for TCC.
        subprocess.run(["codesign", "--force", "--sign", "-", str(app_contents.parent)], capture_output=True, text=True)
        return str(binary)

    def _apple_stt_privacy_guidance(self):
        if self._apple_native_enabled:
            self._apple_native_enabled = False
            self._stop_apple_stt_daemon()
        print("⚠️  Apple STT was blocked by macOS privacy (TCC).")
        print("⚠️  Falling back to non-Apple STT for now.")
        print("   Run these commands, then start Jarvis again to re-prompt permissions:")
        print(f"   tccutil reset SpeechRecognition {APPLE_STT_BUNDLE_ID}")
        print(f"   tccutil reset Microphone {APPLE_STT_BUNDLE_ID}")
        print("   tccutil reset SpeechRecognition com.apple.Terminal")
        print("   tccutil reset Microphone com.apple.Terminal")
        print("   open 'x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition'")
        print("   open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'")
        self._fallback_to_best_nonapple_backend()

    def _fallback_to_best_nonapple_backend(self):
        if self._init_local_backend(explicit_request=False):
            print("✅ Using local Whisper fallback.")
            return
        self._stt_mode = "google"
        print("🧠 STT backend: google")

    def _init_apple_native_backend(self) -> bool:
        mac_ver = platform.mac_ver()[0].strip()
        major = 0
        if mac_ver:
            try:
                major = int(mac_ver.split(".", maxsplit=1)[0])
            except Exception:
                major = 0
        if major >= 26 and not APPLE_STT_FORCE_HELPER:
            print("⚠️  Apple STT helper is unstable on this macOS release due TCC policy. Set JARVIS_FORCE_APPLE_HELPER=1 to override.")
            return False

        binary = self._ensure_apple_stt_binary()
        if not binary:
            return False
        self._apple_stt_binary = binary
        self._apple_native_enabled = True
        self._stt_mode = "apple_native"

        smoke_cmd = [
            self._apple_stt_binary,
            "--max-seconds",
            "1",
            "--startup-timeout",
            "1",
            "--language",
            APPLE_STT_LANGUAGE,
            "--silence-end-ms",
            str(APPLE_STT_SILENCE_END_MS),
            "--min-speech-ms",
            str(APPLE_STT_MIN_SPEECH_MS),
            "--energy-floor",
            str(APPLE_STT_ENERGY_FLOOR),
            "--energy-multiplier",
            str(APPLE_STT_ENERGY_MULTIPLIER),
        ]
        try:
            smoke = subprocess.run(smoke_cmd, capture_output=True, text=True, timeout=6)
        except Exception as exc:
            print(f"⚠️  Apple STT smoke test failed: {exc}. Falling back to Google STT.")
            self._apple_native_enabled = False
            self._stt_mode = "google"
            return False

        if smoke.returncode == 134:
            self._apple_stt_privacy_guidance()
            return False
        if smoke.returncode != 0:
            print("⚠️  Apple STT self-test failed. Falling back to Google STT.")
            self._apple_native_enabled = False
            self._stt_mode = "google"
            return False

        payload = (smoke.stdout or "").strip()
        if payload:
            try:
                parsed = json.loads(payload.splitlines()[-1])
                err = str(parsed.get("error", "")).strip().lower() if isinstance(parsed, dict) else ""
                if "not authorized" in err or "permission" in err:
                    self._apple_stt_privacy_guidance()
                    return False
            except Exception:
                pass

        self._start_apple_stt_daemon()
        if self._apple_daemon_proc and self._apple_daemon_proc.poll() is None:
            print("🧠 STT backend: apple_native (on-device, daemon)")
            return True
        print("⚠️  Apple STT daemon unavailable.")
        self._apple_native_enabled = False
        return False

    def _start_apple_stt_daemon(self):
        if not self._apple_native_enabled or not self._apple_stt_binary:
            return
        proc = self._apple_daemon_proc
        if proc and proc.poll() is None:
            return
        try:
            self._apple_daemon_proc = subprocess.Popen(
                [
                    self._apple_stt_binary,
                    "--daemon",
                    "--language",
                    APPLE_STT_LANGUAGE,
                    "--silence-end-ms",
                    str(APPLE_STT_SILENCE_END_MS),
                    "--min-speech-ms",
                    str(APPLE_STT_MIN_SPEECH_MS),
                    "--energy-floor",
                    str(APPLE_STT_ENERGY_FLOOR),
                    "--energy-multiplier",
                    str(APPLE_STT_ENERGY_MULTIPLIER),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            if self._apple_daemon_proc.stdin is None or self._apple_daemon_proc.stdout is None:
                self._stop_apple_stt_daemon()
        except Exception as exc:
            print(f"⚠️  Failed to start Apple STT daemon: {exc}")
            self._apple_daemon_proc = None

    def _stop_apple_stt_daemon(self):
        proc = self._apple_daemon_proc
        self._apple_daemon_proc = None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _init_local_backend(self, explicit_request: bool) -> bool:
        if np is None:
            if explicit_request:
                print("⚠️  Local STT requested but numpy is missing.")
            return False
        whisper_model_cls = None
        try:
            from faster_whisper import WhisperModel as _WhisperModel
            whisper_model_cls = _WhisperModel
        except Exception as exc:
            if explicit_request:
                print(f"⚠️  Local STT import failed: {exc}.")
            return False
        try:
            self._local_model = whisper_model_cls(LOCAL_STT_MODEL, compute_type=LOCAL_STT_COMPUTE)
            self._local_enabled = True
            self._stt_mode = "local"
            print(f"🧠 STT backend: local ({LOCAL_STT_MODEL}, {LOCAL_STT_COMPUTE})")
            return True
        except Exception as exc:
            if explicit_request:
                print(f"⚠️  Local STT model failed to load: {exc}.")
            return False

    def _init_stt_backend(self):
        requested = STT_BACKEND

        if requested in {"apple_native", "apple", "native"}:
            if self._init_apple_native_backend():
                return
            print("⚠️  Falling back to local/google STT.")
            self._fallback_to_best_nonapple_backend()
            return

        if requested in {"auto"}:
            if self._init_apple_native_backend():
                return
            if self._init_local_backend(explicit_request=False):
                return
            self._stt_mode = "google"
            print("🧠 STT backend: google")
            return

        if requested == "local":
            if self._init_local_backend(explicit_request=True):
                return
            print("⚠️  Falling back to Google STT.")
            self._stt_mode = "google"
            print("🧠 STT backend: google")
            return

        self._stt_mode = "google"
        print("🧠 STT backend: google")

    def _parse_apple_stt_payload(self, payload: str, elapsed_ms: int) -> tuple[str, dict[str, int]]:
        parsed: dict[str, Any]
        try:
            parsed = json.loads(payload.splitlines()[-1])
        except Exception:
            return payload, {"speech_end_to_transcript_ms": elapsed_ms}

        if not isinstance(parsed, dict):
            return "", {"speech_end_to_transcript_ms": elapsed_ms}

        error = str(parsed.get("error", "")).strip()
        if error:
            print(f"⚠️  Apple STT: {error}")

        text = str(parsed.get("text", "")).strip()
        capture: dict[str, int] = {}
        first_speech_ms = parsed.get("first_speech_ms")
        if isinstance(first_speech_ms, (int, float)):
            capture["cue_to_speech_start_ms"] = int(first_speech_ms)

        end_to_text_ms = parsed.get("speech_end_to_transcript_ms")
        if isinstance(end_to_text_ms, (int, float)):
            capture["speech_end_to_transcript_ms"] = int(end_to_text_ms)
        else:
            recognition_total_ms = parsed.get("recognition_total_ms")
            if isinstance(recognition_total_ms, (int, float)):
                capture["speech_end_to_transcript_ms"] = int(recognition_total_ms)
            else:
                capture["speech_end_to_transcript_ms"] = elapsed_ms

        speech_duration_ms = parsed.get("speech_duration_ms")
        if isinstance(speech_duration_ms, (int, float)):
            capture["speech_duration_ms"] = int(speech_duration_ms)

        return text, capture

    def _decode_apple_native_daemon(
        self,
        max_record_seconds: int,
        startup_timeout_s: int,
    ) -> tuple[str, dict[str, int]] | None:
        timeout_s = max_record_seconds + APPLE_STT_TIMEOUT_PADDING_S
        with self._apple_daemon_lock:
            self._start_apple_stt_daemon()
            proc = self._apple_daemon_proc
            if not proc:
                return None
            if proc.poll() is not None:
                if proc.returncode == 134:
                    self._apple_stt_privacy_guidance()
                return None
            if proc.stdin is None or proc.stdout is None:
                return None

            request = {
                "max_seconds": max_record_seconds,
                "startup_timeout": startup_timeout_s,
                "language": APPLE_STT_LANGUAGE,
                "silence_end_ms": APPLE_STT_SILENCE_END_MS,
                "min_speech_ms": APPLE_STT_MIN_SPEECH_MS,
                "energy_floor": APPLE_STT_ENERGY_FLOOR,
                "energy_multiplier": APPLE_STT_ENERGY_MULTIPLIER,
            }
            started = time.time()
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                print(f"⚠️  Apple STT daemon write failed: {exc}")
                self._stop_apple_stt_daemon()
                return None

            try:
                ready, _, _ = select.select([proc.stdout], [], [], timeout_s)
            except Exception:
                ready = []
            elapsed_ms = int((time.time() - started) * 1000)
            if not ready:
                if proc.poll() == 134:
                    self._apple_stt_privacy_guidance()
                    return "", {"speech_end_to_transcript_ms": elapsed_ms}
                print("⚠️  Apple STT daemon timed out. Restarting daemon.")
                self._stop_apple_stt_daemon()
                return "", {"speech_end_to_transcript_ms": elapsed_ms}

            line = proc.stdout.readline().strip()
            if not line:
                if proc.poll() == 134:
                    self._apple_stt_privacy_guidance()
                return "", {"speech_end_to_transcript_ms": elapsed_ms}
            return self._parse_apple_stt_payload(line, elapsed_ms)

    def _decode_apple_native_oneshot(
        self,
        max_record_seconds: int,
        startup_timeout_s: int,
    ) -> tuple[str, dict[str, int]]:
        if not self._apple_native_enabled or not self._apple_stt_binary:
            return "", {}
        cmd = [
            self._apple_stt_binary,
            "--max-seconds", str(max_record_seconds),
            "--startup-timeout", str(startup_timeout_s),
            "--language", APPLE_STT_LANGUAGE,
            "--silence-end-ms", str(APPLE_STT_SILENCE_END_MS),
            "--min-speech-ms", str(APPLE_STT_MIN_SPEECH_MS),
            "--energy-floor", str(APPLE_STT_ENERGY_FLOOR),
            "--energy-multiplier", str(APPLE_STT_ENERGY_MULTIPLIER),
        ]
        started = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max_record_seconds + APPLE_STT_TIMEOUT_PADDING_S,
            )
        except subprocess.TimeoutExpired:
            return "", {"speech_end_to_transcript_ms": int((time.time() - started) * 1000)}
        except Exception as exc:
            print(f"⚠️  Apple STT invoke error: {exc}")
            return "", {"speech_end_to_transcript_ms": int((time.time() - started) * 1000)}

        elapsed_ms = int((time.time() - started) * 1000)
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            if err:
                print(f"⚠️  Apple STT error: {err[:220]}")
            if result.returncode == 134:
                self._apple_stt_privacy_guidance()
            return "", {"speech_end_to_transcript_ms": elapsed_ms}

        payload = (result.stdout or "").strip()
        if not payload:
            return "", {"speech_end_to_transcript_ms": elapsed_ms}

        return self._parse_apple_stt_payload(payload, elapsed_ms)

    def _decode_apple_native(
        self,
        max_record_seconds: int,
        startup_timeout_s: int,
    ) -> tuple[str, dict[str, int]]:
        daemon_result = self._decode_apple_native_daemon(max_record_seconds, startup_timeout_s)
        if daemon_result is not None:
            return daemon_result
        return self._decode_apple_native_oneshot(max_record_seconds, startup_timeout_s)

    def _decode_local(self, raw: bytes, partial: bool = False) -> str:
        if not self._local_enabled or self._local_model is None or not raw or np is None:
            return ""
        try:
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            beam_size = 1 if partial else max(1, LOCAL_STT_BEAM_SIZE)
            best_of = 1 if partial else max(1, LOCAL_STT_BEST_OF)
            initial_prompt = None if partial else (LOCAL_STT_INITIAL_PROMPT or None)
            condition_on_previous = False if partial else LOCAL_STT_CONDITION_ON_PREVIOUS
            segments, _ = self._local_model.transcribe(
                pcm,
                language="en",
                beam_size=beam_size,
                best_of=best_of,
                without_timestamps=True,
                condition_on_previous_text=condition_on_previous,
                vad_filter=False,
                temperature=0.0,
                initial_prompt=initial_prompt,
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

    def listen(
        self,
        max_record_seconds: int | None = None,
        startup_timeout_s: int | None = None,
        announce: bool = True,
        show_partials: bool = True,
        show_transcript: bool = True,
    ) -> str:
        requested_max = max_record_seconds or MAX_RECORD_SECONDS
        requested_startup = startup_timeout_s or STARTUP_TIMEOUT_S
        show_partials = show_partials and SHOW_PARTIALS
        if self._apple_native_enabled:
            if announce:
                print("👂 Listening (Apple Speech)…")
                print("🔄 Recognising…")
            text, capture = self._decode_apple_native(
                max_record_seconds=requested_max,
                startup_timeout_s=requested_startup,
            )
            if show_transcript and text:
                print(f'📝 You said: "{text}"')
            self.last_capture_info = capture
            return text

        started_at = time.time()
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
        partial_updates = 0
        partial_suppressed_notice = False
        max_frames   = int(requested_max * 1000 / VAD_FRAME_MS)
        wait_frames  = int(requested_startup * 1000 / VAD_FRAME_MS)
        speech_started_at: float | None = None

        if announce:
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
                        speech_started_at = time.time()
                        silence_ct = 0
                        if announce:
                            print("🗨  Capturing speech…")
                    elif total > wait_frames:          # no speech in time
                        break
                else:
                    speech_buf.append(frame)
                    speech_frames += 1
                    if not is_speech:
                        silence_ct += 1
                        if silence_ct >= SILENCE_END_FRAMES:
                            if announce:
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
                            if show_partials and partial_updates < LOCAL_STT_PARTIAL_MAX_UPDATES:
                                print(f'📝 Partial: "{partial}"')
                                partial_updates += 1
                            elif show_partials and not partial_suppressed_notice:
                                print("📝 Partial: … (suppressed)")
                                partial_suppressed_notice = True
        finally:
            stream.stop_stream()
            stream.close()

        if not triggered or len(speech_buf) < MIN_SPEECH_FRAMES:
            self.last_capture_info = {}
            return ""

        speech_ended_at = time.time()
        raw = b"".join(speech_buf)
        self._debug_dump_audio(raw, VAD_SAMPLE_RATE)
        if announce:
            print("🔄 Recognising…")

        # Prefer local low-latency STT if available.
        if self._local_enabled:
            text = self._decode_local(raw, partial=False)
            if show_transcript:
                print(f'📝 You said: "{text}"')
            if text:
                self.last_capture_info = {
                    "cue_to_speech_start_ms": int(((speech_started_at or speech_ended_at) - started_at) * 1000),
                    "speech_end_to_transcript_ms": int((time.time() - speech_ended_at) * 1000),
                    "speech_duration_ms": int((speech_ended_at - (speech_started_at or speech_ended_at)) * 1000),
                }
                return text

        text = self._decode_google(raw)
        if text:
            if show_transcript:
                print(f'📝 You said: "{text}"')
        self.last_capture_info = {
            "cue_to_speech_start_ms": int(((speech_started_at or speech_ended_at) - started_at) * 1000),
            "speech_end_to_transcript_ms": int((time.time() - speech_ended_at) * 1000),
            "speech_duration_ms": int((speech_ended_at - (speech_started_at or speech_ended_at)) * 1000),
        }
        return text

    def close(self):
        self._stop_apple_stt_daemon()
        try:
            self._pa.terminate()
        except Exception:
            pass


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


def _match_known_app(query_lower: str) -> str | None:
    for key, app in KNOWN_APPS.items():
        if re.search(rf"\\b{re.escape(key)}\\b", query_lower):
            return app
    return None


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
ACTION_GIT_DIFF_STAT = "git_diff_stat"
ACTION_GIT_LOG_RECENT = "git_log_recent"
ACTION_GIT_BRANCHES = "git_branches"
ACTION_GIT_RECENT_CHANGES = "git_recent_changes"
ACTION_PROJECT_SEARCH = "project_search"
ACTION_BATTERY_STATUS = "battery_status"
ACTION_VOLUME_STATUS = "volume_status"
ACTION_NOW_PLAYING = "now_playing"
ACTION_WIFI_STATUS = "wifi_status"
ACTION_TIME_STATUS = "time_status"
ACTION_ACTIVE_APP = "active_app"
ACTION_TRANSLATE_TEXT = "translate_text"
ACTION_SET_VOLUME_LEVEL = "set_volume_level"
ACTION_TOGGLE_MUTE = "toggle_mute"
ACTION_QUIT_APP = "quit_app"
ACTION_FOCUS_APP = "focus_app"
ACTION_OPEN_URL = "open_url"

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
    ACTION_GIT_DIFF_STAT,
    ACTION_GIT_LOG_RECENT,
    ACTION_GIT_BRANCHES,
    ACTION_GIT_RECENT_CHANGES,
    ACTION_PROJECT_SEARCH,
    ACTION_BATTERY_STATUS,
    ACTION_VOLUME_STATUS,
    ACTION_NOW_PLAYING,
    ACTION_WIFI_STATUS,
    ACTION_TIME_STATUS,
    ACTION_ACTIVE_APP,
    ACTION_TRANSLATE_TEXT,
    ACTION_SET_VOLUME_LEVEL,
    ACTION_TOGGLE_MUTE,
    ACTION_QUIT_APP,
    ACTION_FOCUS_APP,
    ACTION_OPEN_URL,
}

ACTION_CATEGORIES: dict[str, set[str]] = {
    "fs": {
        ACTION_CREATE_FOLDER,
        ACTION_CREATE_FILE,
        ACTION_LIST_PATH,
        ACTION_FIND_NAME,
        ACTION_MOVE_PATH,
        ACTION_COPY_PATH,
        ACTION_RENAME_PATH,
        ACTION_DELETE_PATH,
    },
    "status": {
        ACTION_DISK_USAGE,
        ACTION_BATTERY_STATUS,
        ACTION_VOLUME_STATUS,
        ACTION_NOW_PLAYING,
        ACTION_WIFI_STATUS,
        ACTION_TIME_STATUS,
        ACTION_ACTIVE_APP,
    },
    "dev": {
        ACTION_GIT_STATUS,
        ACTION_GIT_DIFF_STAT,
        ACTION_GIT_LOG_RECENT,
        ACTION_GIT_BRANCHES,
        ACTION_GIT_RECENT_CHANGES,
        ACTION_PROJECT_SEARCH,
    },
    "language": {
        ACTION_TRANSLATE_TEXT,
    },
    "macos": {
        ACTION_SET_VOLUME_LEVEL,
        ACTION_TOGGLE_MUTE,
        ACTION_QUIT_APP,
        ACTION_FOCUS_APP,
        ACTION_OPEN_URL,
    },
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


class TranslatorBackend:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        raise NotImplementedError


class LocalDictionaryTranslator(TranslatorBackend):
    _phrases = {
        ("english", "spanish"): {
            "hello": "hola",
            "how are you": "como estas",
            "what is up": "que pasa",
            "good morning": "buenos dias",
            "good night": "buenas noches",
            "thank you": "gracias",
        },
        ("english", "french"): {
            "hello": "bonjour",
            "how are you": "comment ca va",
            "good morning": "bonjour",
            "good night": "bonne nuit",
            "thank you": "merci",
        },
    }

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        src = source_lang.lower().strip()
        dst = target_lang.lower().strip()
        key = (src, dst)
        lookup = self._phrases.get(key, {})
        normalized = text.lower().strip()
        if normalized in lookup:
            return lookup[normalized]

        # Best-effort word-by-word fallback for small local dictionary.
        word_map = {}
        for phrase, translated in lookup.items():
            if " " not in phrase and " " not in translated:
                word_map[phrase] = translated
        if word_map:
            translated_words = [word_map.get(token.lower(), token) for token in text.split()]
            return " ".join(translated_words)
        return ""


class WakeWordEngine:
    def wait_for_wake(self) -> bool:
        raise NotImplementedError

    def close(self):
        return None


class STTPhraseWakeWordEngine(WakeWordEngine):
    def __init__(self, mic: "SmartMic"):
        self._mic = mic
        self._last_hit_monotonic = 0.0

    def _match_wake_phrase(self, heard: str) -> bool:
        cleaned = re.sub(r"[^a-zA-Z\s]", " ", heard).lower()
        words = [w for w in cleaned.split() if w]
        if not words or len(words) > WAKEWORD_MAX_WORDS:
            return False
        phrase = " ".join(words)
        return phrase in {"jarvis", "hey jarvis", "hello jarvis", "yo jarvis"}

    def wait_for_wake(self) -> bool:
        if _recent_tts_activity(WAKEWORD_TTS_GUARD_MS):
            time.sleep(0.1)
            return False
        heard = self._mic.listen(
            max_record_seconds=4,
            startup_timeout_s=4,
            announce=False,
            show_partials=False,
            show_transcript=False,
        )
        if not heard:
            return False
        if not self._match_wake_phrase(heard):
            return False
        now = time.monotonic()
        if ((now - self._last_hit_monotonic) * 1000.0) < float(WAKEWORD_MIN_INTERVAL_MS):
            return False
        self._last_hit_monotonic = now
        return True


class OpenWakeWordEngine(WakeWordEngine):
    def __init__(self, fallback: WakeWordEngine):
        self._fallback = fallback
        self._available = False
        self._last_hit_monotonic = 0.0
        self._pa: pyaudio.PyAudio | None = None
        self._stream: Any = None
        self._model = None
        self._frame_samples = int(VAD_SAMPLE_RATE * 0.08)  # 80ms
        try:
            if np is None:
                raise RuntimeError("numpy unavailable")
            from openwakeword.model import Model  # type: ignore

            self._model = Model()
            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=VAD_SAMPLE_RATE,
                input=True,
                frames_per_buffer=self._frame_samples,
            )
            self._available = True
        except Exception as exc:
            print(f"⚠️  openWakeWord unavailable: {exc}. Falling back to stt_phrase.")
            self._model = None

    def _score_frame(self, frame: bytes) -> float:
        if np is None or self._model is None:
            return 0.0
        pcm_i16 = np.frombuffer(frame, dtype=np.int16)
        pcm_f32 = pcm_i16.astype(np.float32) / 32768.0

        score_obj: Any = None
        try:
            score_obj = self._model.predict(pcm_f32)
        except Exception:
            try:
                score_obj = self._model.predict(pcm_i16)
            except Exception:
                return 0.0

        if isinstance(score_obj, dict):
            numeric_scores = [float(v) for v in score_obj.values() if isinstance(v, (int, float))]
            return max(numeric_scores) if numeric_scores else 0.0
        if isinstance(score_obj, (int, float)):
            return float(score_obj)
        return 0.0

    def wait_for_wake(self) -> bool:
        if _recent_tts_activity(WAKEWORD_TTS_GUARD_MS):
            time.sleep(0.08)
            return False
        if not self._available:
            return self._fallback.wait_for_wake()

        deadline = time.monotonic() + max(0.2, WAKEWORD_POLL_SECONDS)
        try:
            while time.monotonic() < deadline:
                frame = self._stream.read(self._frame_samples, exception_on_overflow=False)
                score = self._score_frame(frame)
                if score >= WAKEWORD_THRESHOLD:
                    now = time.monotonic()
                    if ((now - self._last_hit_monotonic) * 1000.0) < float(WAKEWORD_MIN_INTERVAL_MS):
                        continue
                    self._last_hit_monotonic = now
                    return True
        except Exception as exc:
            print(f"⚠️  openWakeWord stream failed: {exc}. Switching to stt_phrase.")
            self.close()
            self._available = False
            return self._fallback.wait_for_wake()
        return False

    def close(self):
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._pa = None


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
_translator_backend: TranslatorBackend | None = None
_translator_lock = threading.Lock()

_LATENCY_BUDGET_MS = {
    "cue_to_speech_start": 250,
    "speech_duration": 4500,
    "speech_end_to_transcript": 700,
    "transcript_to_response": 500,
    "post_speech_to_response": 1200,
}


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


def _latency_metric(stage: str, value_ms: int):
    _metric("latency.stage_ms", value_ms, {"stage": stage})
    budget = _LATENCY_BUDGET_MS.get(stage)
    if budget and value_ms > budget:
        print(f"⚠️  Latency warning: {stage}={value_ms}ms (budget {budget}ms)")


def _print_turn_timers(
    capture: dict[str, int],
    *,
    transcript_to_response_ms: int | None,
    total_ms: int,
    had_text: bool,
):
    if not SHOW_TURN_TIMERS:
        return
    cue_ms = int(capture.get("cue_to_speech_start_ms", 0))
    speech_ms = int(capture.get("speech_duration_ms", 0))
    stt_ms = int(capture.get("speech_end_to_transcript_ms", 0))
    post_speech_ms = (stt_ms + transcript_to_response_ms) if transcript_to_response_ms is not None else None
    parts = [
        f"start={cue_ms}ms",
        f"speech={speech_ms}ms",
        f"stt={stt_ms}ms",
    ]
    if transcript_to_response_ms is not None:
        parts.append(f"route={transcript_to_response_ms}ms")
    if post_speech_ms is not None:
        parts.append(f"post_speech={post_speech_ms}ms")
    parts.append(f"total={int(total_ms)}ms")
    if not had_text:
        parts.append("transcript=empty")
    print("⏱  Turn: " + " | ".join(parts))


def _get_translator_backend() -> TranslatorBackend:
    global _translator_backend
    with _translator_lock:
        if _translator_backend is not None:
            return _translator_backend
        # v1 local-core uses a local translator first.
        _translator_backend = LocalDictionaryTranslator()
        return _translator_backend


def _translate_text_local(text: str, target_lang: str, source_lang: str = "english") -> str:
    translator = _get_translator_backend()
    return translator.translate(text=text, source_lang=source_lang, target_lang=target_lang)


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


def _parse_translation_request(query: str) -> tuple[str, str, str] | None:
    raw = query.strip()
    lower = raw.lower()

    # translate "hello" to spanish
    quoted = re.search(r'translate\s+"(.+?)"\s+to\s+([a-zA-Z]+)', raw, flags=re.IGNORECASE)
    if quoted:
        return quoted.group(1).strip(), "english", quoted.group(2).strip().lower()

    # translate hello to spanish
    plain = re.search(r'translate\s+(.+?)\s+to\s+([a-zA-Z]+)$', raw, flags=re.IGNORECASE)
    if plain:
        return plain.group(1).strip().strip("'\""), "english", plain.group(2).strip().lower()

    # say this in spanish: hello
    say_in = re.search(r'say\s+this\s+in\s+([a-zA-Z]+)\s*[:,-]?\s*(.+)$', raw, flags=re.IGNORECASE)
    if say_in:
        return say_in.group(2).strip().strip("'\""), "english", say_in.group(1).strip().lower()

    if lower.startswith("translate ") and " to " not in lower:
        text = raw[len("translate "):].strip().strip("'\"")
        if text:
            return text, "english", TRANSLATION_DEFAULT_TARGET
    return None


def _tokenize_lower(text: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split() if w]


def _has_close_token(tokens: list[str], targets: list[str], cutoff: float = 0.74) -> bool:
    for token in tokens:
        if difflib.get_close_matches(token, targets, n=1, cutoff=cutoff):
            return True
    return False


def _build_action_request(query: str) -> ActionRequest | None:
    text = query.strip()
    lower = text.lower()
    tokens = _tokenize_lower(text)
    principal = _principal()

    parsed_translation = _parse_translation_request(text)
    if parsed_translation:
        source_text, source_lang, target_lang = parsed_translation
        return ActionRequest(
            action=ACTION_TRANSLATE_TEXT,
            args={"text": source_text, "source_lang": source_lang, "target_lang": target_lang},
            principal=principal,
            reason=text,
        )

    vol_set = re.search(r"\bset\s+(?:the\s+)?volume\s+(?:to|at)\s+(\d+)", lower)
    if vol_set:
        level = max(0, min(100, int(vol_set.group(1))))
        return ActionRequest(
            action=ACTION_SET_VOLUME_LEVEL,
            args={"level": level},
            principal=principal,
            reason=text,
        )

    if re.search(r"\b(mute (?:my )?(?:volume|sound|audio)|turn (?:the )?sound off)\b", lower):
        return ActionRequest(
            action=ACTION_TOGGLE_MUTE,
            args={"mute": True},
            principal=principal,
            reason=text,
        )

    if re.search(r"\b(unmute (?:my )?(?:volume|sound|audio)|turn (?:the )?sound on)\b", lower):
        return ActionRequest(
            action=ACTION_TOGGLE_MUTE,
            args={"mute": False},
            principal=principal,
            reason=text,
        )

    if re.search(r'\b(disk\s+space|storage|disk\s+usage)\b', lower):
        return ActionRequest(action=ACTION_DISK_USAGE, args={}, principal=principal, reason=text)

    if re.search(r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count|charging|power adapter|ac attached)\b', lower):
        return ActionRequest(action=ACTION_BATTERY_STATUS, args={}, principal=principal, reason=text)

    if re.search(r'\b(volume level|what.*volume|volume status|current volume|sound level)\b', lower):
        return ActionRequest(action=ACTION_VOLUME_STATUS, args={}, principal=principal, reason=text)

    song_phrase = re.search(r'\b(what song|what.?s.*playing|song.*playing|now playing|currently(?:\s+being)?\s+played|currently.*playing|track playing|current song|being played)\b', lower)
    approx_song_status = (
        ("song" in tokens or "track" in tokens)
        and not lower.strip().startswith("play ")
        and (
            _has_close_token(tokens, ["playing", "played", "currently", "current", "now"], cutoff=0.66)
            or len(tokens) <= 3
        )
    )
    if song_phrase or approx_song_status:
        return ActionRequest(action=ACTION_NOW_PLAYING, args={}, principal=principal, reason=text)

    if re.search(r'\b(wi[- ]?fi|wireless network|network name|network am i on|what network|ssid|internet(?:\s+connection)?|connected to (?:the )?internet|am i online|connected online)\b', lower):
        return ActionRequest(action=ACTION_WIFI_STATUS, args={}, principal=principal, reason=text)

    if re.search(r'\b(what time|time now|current time|date today|today.?s date)\b', lower):
        return ActionRequest(action=ACTION_TIME_STATUS, args={}, principal=principal, reason=text)

    if re.search(r'\b(active app|frontmost app|which app.*open|focused app|what app is active|which app is running|currently running app|active .* currently running)\b', lower):
        return ActionRequest(action=ACTION_ACTIVE_APP, args={}, principal=principal, reason=text)

    match = re.search(r'\bgit\s+status(?:\s+in\s+(.+))?$', lower)
    if match:
        repo = _normalize_path(match.group(1) or os.getcwd())
        return ActionRequest(action=ACTION_GIT_STATUS, args={"repo": repo}, principal=principal, reason=text)

    if re.search(r'\bgit\s+diff\b', lower):
        repo_match = re.search(r'\bin\s+(.+)$', lower)
        repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
        return ActionRequest(
            action=ACTION_GIT_DIFF_STAT,
            args={"repo": repo},
            principal=principal,
            reason=text,
        )

    if re.search(r'\bgit\s+log\b', lower):
        repo_match = re.search(r'\bin\s+(.+)$', lower)
        repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
        limit_match = re.search(r'\blast\s+(\d+)\b', lower)
        limit = int(limit_match.group(1)) if limit_match else 5
        limit = max(1, min(50, limit))
        return ActionRequest(
            action=ACTION_GIT_LOG_RECENT,
            args={"repo": repo, "limit": limit},
            principal=principal,
            reason=text,
        )

    if re.search(r'\bgit\s+branches\b', lower) or re.search(r'\b(list|show)\s+branches\b', lower):
        repo_match = re.search(r'\bin\s+(.+)$', lower)
        repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
        return ActionRequest(
            action=ACTION_GIT_BRANCHES,
            args={"repo": repo},
            principal=principal,
            reason=text,
        )

    recent_changes = re.search(r'\bwhat (?:has )?changed since (?:the )?last commit\b', lower)
    if recent_changes:
        repo_match = re.search(r'\bin\s+(.+)$', lower)
        repo = _normalize_path(repo_match.group(1)) if repo_match else os.getcwd()
        return ActionRequest(
            action=ACTION_GIT_RECENT_CHANGES,
            args={"repo": repo},
            principal=principal,
            reason=text,
        )

    search_match = re.search(r'\bsearch\s+for\s+(.+?)\s+in\s+(.+)$', text, flags=re.IGNORECASE)
    if search_match:
        pattern = search_match.group(1).strip().strip("'\"")
        root = _normalize_path(search_match.group(2))
        if pattern:
            return ActionRequest(
                action=ACTION_PROJECT_SEARCH,
                args={"pattern": pattern, "path": root},
                principal=principal,
                reason=text,
            )

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

    if re.search(r'\b(quit|close)\b', lower):
        app = _match_known_app(lower)
        if app:
            return ActionRequest(
                action=ACTION_QUIT_APP,
                args={"app": app},
                principal=principal,
                reason=text,
            )

    if re.search(r'\b(focus|activate|switch to)\b', lower):
        app = _match_known_app(lower)
        if app:
            return ActionRequest(
                action=ACTION_FOCUS_APP,
                args={"app": app},
                principal=principal,
                reason=text,
            )

    url_match = re.search(r'\bopen\s+url\s+(\S+)', text, flags=re.IGNORECASE)
    if url_match:
        url = url_match.group(1).strip().strip("'\"")
        if url.lower().startswith(("http://", "https://")):
            return ActionRequest(
                action=ACTION_OPEN_URL,
                args={"url": url},
                principal=principal,
                reason=text,
            )

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
    if action == ACTION_GIT_STATUS:
        return f"git status in {_shorten(args.get('repo', ''))}"
    if action == ACTION_GIT_DIFF_STAT:
        return f"git diff stat in {_shorten(args.get('repo', ''))}"
    if action == ACTION_GIT_LOG_RECENT:
        count = args.get("limit", 5)
        return f"git log last {count} in {_shorten(args.get('repo', ''))}"
    if action == ACTION_GIT_BRANCHES:
        return f"git branches in {_shorten(args.get('repo', ''))}"
    if action == ACTION_GIT_RECENT_CHANGES:
        return f"recent changes since last commit in {_shorten(args.get('repo', ''))}"
    if action == ACTION_PROJECT_SEARCH:
        return f"search '{_shorten(args.get('pattern', ''))}' in {_shorten(args.get('path', ''))}"
    if action == ACTION_BATTERY_STATUS:
        return "check battery status and health"
    if action == ACTION_VOLUME_STATUS:
        return "check output volume"
    if action == ACTION_SET_VOLUME_LEVEL:
        return f"set volume to {args.get('level', 0)} percent"
    if action == ACTION_TOGGLE_MUTE:
        return "mute volume" if args.get("mute", True) else "unmute volume"
    if action == ACTION_NOW_PLAYING:
        return "check current song"
    if action == ACTION_WIFI_STATUS:
        return "check wifi status"
    if action == ACTION_TIME_STATUS:
        return "check current date and time"
    if action == ACTION_ACTIVE_APP:
        return "check active app"
    if action == ACTION_TRANSLATE_TEXT:
        return f"translate text to {args.get('target_lang', TRANSLATION_DEFAULT_TARGET)}"
    if action == ACTION_QUIT_APP:
        return f"quit app {args.get('app', '')}"
    if action == ACTION_FOCUS_APP:
        return f"focus app {args.get('app', '')}"
    if action == ACTION_OPEN_URL:
        return f"open url {_shorten(args.get('url', ''))}"
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

    if request.action in {
        ACTION_GIT_STATUS,
        ACTION_GIT_DIFF_STAT,
        ACTION_GIT_LOG_RECENT,
        ACTION_GIT_BRANCHES,
        ACTION_GIT_RECENT_CHANGES,
    }:
        repo = request.args.get("repo", "")
        if not _is_under_home(repo):
            return PolicyDecision(False, "git command outside home blocked")

    if request.action == ACTION_PROJECT_SEARCH:
        root = request.args.get("path", "")
        if not _is_under_home(root):
            return PolicyDecision(False, "project search outside home blocked")

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


def _run_set_volume_level_action(level: int) -> ActionResult:
    started = time.time()
    script = f'set volume output volume {level}'
    result = _run_safe_process(["osascript", "-e", script], timeout=6)
    summary = f"Output volume set to {level} percent."
    return ActionResult(
        ok=result.ok,
        return_code=result.return_code,
        stdout=summary if result.ok else "",
        stderr=result.stderr,
        duration_ms=int((time.time() - started) * 1000),
        command_repr=script,
    )


def _run_toggle_mute_action(mute: bool) -> ActionResult:
    started = time.time()
    script = f"set volume output muted {'true' if mute else 'false'}"
    result = _run_safe_process(["osascript", "-e", script], timeout=6)
    summary = "Output muted." if mute else "Output unmuted."
    return ActionResult(
        ok=result.ok,
        return_code=result.return_code,
        stdout=summary if result.ok else "",
        stderr=result.stderr,
        duration_ms=int((time.time() - started) * 1000),
        command_repr=script,
    )


def _run_volume_status_action() -> ActionResult:
    started = time.time()
    script = 'output volume of (get volume settings) & "|" & output muted of (get volume settings)'
    result = _run_safe_process(["osascript", "-e", script], timeout=6)
    if result.ok and result.stdout:
        try:
            volume_raw, muted_raw = result.stdout.split("|", maxsplit=1)
            volume = volume_raw.strip()
            muted = muted_raw.strip().lower() == "true"
            summary = f"Output volume is {volume} percent. {'Muted.' if muted else 'Not muted.'}"
            return ActionResult(True, 0, summary, "", int((time.time() - started) * 1000), result.command_repr)
        except Exception:
            pass
    return result


def _run_now_playing_action() -> ActionResult:
    started = time.time()
    spotify_script = (
        'try\n'
        'tell application "Spotify" to if player state is playing then return name of current track & " by " & artist of current track\n'
        'end try'
    )
    spotify = _run_safe_process(["osascript", "-e", spotify_script], timeout=6)
    if spotify.ok and spotify.stdout:
        return ActionResult(True, 0, f"Now playing: {spotify.stdout}.", "", int((time.time() - started) * 1000), spotify.command_repr)

    music_script = (
        'try\n'
        'tell application "Music" to if player state is playing then return name of current track & " by " & artist of current track\n'
        'end try'
    )
    music = _run_safe_process(["osascript", "-e", music_script], timeout=6)
    if music.ok and music.stdout:
        return ActionResult(True, 0, f"Now playing: {music.stdout}.", "", int((time.time() - started) * 1000), music.command_repr)

    return ActionResult(
        ok=False,
        return_code=1,
        stdout="",
        stderr="Could not verify a currently playing song.",
        duration_ms=int((time.time() - started) * 1000),
        command_repr="osascript now-playing",
    )


def _detect_wifi_device() -> str:
    ports = _run_safe_process(["networksetup", "-listallhardwareports"], timeout=8)
    if not ports.ok:
        return "en0"
    blocks = ports.stdout.split("\n\n")
    for block in blocks:
        if "Hardware Port: Wi-Fi" in block:
            for line in block.splitlines():
                if line.strip().startswith("Device:"):
                    return line.split(":", maxsplit=1)[1].strip()
    return "en0"


def _run_wifi_status_action() -> ActionResult:
    started = time.time()
    device = _detect_wifi_device()
    status = _run_safe_process(["networksetup", "-getairportnetwork", device], timeout=8)
    if status.ok and status.stdout:
        line = status.stdout.strip()
        if "Current Wi-Fi Network" in line:
            ssid = line.split(":", maxsplit=1)[1].strip()
            summary = f"Wi-Fi is connected to {ssid}."
        else:
            summary = f"Wi-Fi status: {line}."
        return ActionResult(True, 0, summary, "", int((time.time() - started) * 1000), status.command_repr)
    return ActionResult(False, 1, "", "Could not verify Wi-Fi status.", int((time.time() - started) * 1000), status.command_repr)


def _run_time_status_action() -> ActionResult:
    now = datetime.datetime.now()
    return ActionResult(
        ok=True,
        return_code=0,
        stdout=now.strftime("It is %I:%M %p on %A, %B %d, %Y."),
        stderr="",
        duration_ms=1,
        command_repr="local datetime",
    )


def _run_active_app_action() -> ActionResult:
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    result = _run_safe_process(["osascript", "-e", script], timeout=6)
    if result.ok and result.stdout:
        return ActionResult(True, 0, f"Active app is {result.stdout}.", "", result.duration_ms, result.command_repr)
    return ActionResult(False, 1, "", "Could not verify active app.", result.duration_ms, result.command_repr)


def _run_translate_action(args: dict[str, Any]) -> ActionResult:
    started = time.time()
    source_text = str(args.get("text", "")).strip()
    source_lang = str(args.get("source_lang", "english")).strip().lower()
    target_lang = str(args.get("target_lang", TRANSLATION_DEFAULT_TARGET)).strip().lower()
    if not source_text:
        return ActionResult(False, 1, "", "Missing text to translate.", int((time.time() - started) * 1000), "translate")

    translated = _translate_text_local(text=source_text, source_lang=source_lang, target_lang=target_lang)
    if translated:
        return ActionResult(
            True,
            0,
            f"In {target_lang}: {translated}",
            "",
            int((time.time() - started) * 1000),
            f"translate {source_lang}->{target_lang}",
        )
    return ActionResult(
        False,
        1,
        "",
        f"Could not verify local translation for {source_lang} to {target_lang}.",
        int((time.time() - started) * 1000),
        f"translate {source_lang}->{target_lang}",
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
    if action == ACTION_GIT_DIFF_STAT:
        return _run_safe_process(["git", "-C", args["repo"], "diff", "--stat"])
    if action == ACTION_GIT_LOG_RECENT:
        limit = int(args.get("limit", 5))
        return _run_safe_process(["git", "-C", args["repo"], "log", f"-n{limit}", "--oneline"])
    if action == ACTION_GIT_BRANCHES:
        return _run_safe_process(["git", "-C", args["repo"], "branch", "--all", "--color=never"])
    if action == ACTION_GIT_RECENT_CHANGES:
        return _run_safe_process(["git", "-C", args["repo"], "diff", "--stat", "HEAD~1..HEAD"])
    if action == ACTION_PROJECT_SEARCH:
        # Limit output size via ripgrep options to keep summaries fast.
        return _run_safe_process(
            ["rg", "--max-count", "200", "--no-heading", "--color", "never", args["pattern"], args["path"]],
            timeout=ACTION_TIMEOUT_SECONDS,
        )
    if action == ACTION_BATTERY_STATUS:
        return _run_battery_status_action()
    if action == ACTION_VOLUME_STATUS:
        return _run_volume_status_action()
    if action == ACTION_SET_VOLUME_LEVEL:
        return _run_set_volume_level_action(int(args["level"]))
    if action == ACTION_TOGGLE_MUTE:
        return _run_toggle_mute_action(bool(args.get("mute", True)))
    if action == ACTION_NOW_PLAYING:
        return _run_now_playing_action()
    if action == ACTION_WIFI_STATUS:
        return _run_wifi_status_action()
    if action == ACTION_TIME_STATUS:
        return _run_time_status_action()
    if action == ACTION_ACTIVE_APP:
        return _run_active_app_action()
    if action == ACTION_TRANSLATE_TEXT:
        return _run_translate_action(args)
    if action == ACTION_GIT_STATUS:
        return _run_safe_process(["git", "-C", args["repo"], "status", "--short"])
    if action == ACTION_QUIT_APP:
        script = f'tell application "{args["app"]}" to quit'
        return _run_safe_process(["osascript", "-e", script])
    if action == ACTION_FOCUS_APP:
        script = f'tell application "{args["app"]}" to activate'
        return _run_safe_process(["osascript", "-e", script])
    if action == ACTION_OPEN_URL:
        return _run_safe_process(["open", args["url"]])

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
        system=SUMMARY_SYSTEM_PROMPT,
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

    total_steps = len(plan.requests)
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

        try:
            speak(f"Running step {idx} of {total_steps}: {_describe_action_request(request)}.")
        except Exception as exc:
            print(f"⚠️  TTS error before mission step {idx}: {exc}")

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
        return (
            "I can run structured actions like create, list, find, move, copy, delete, "
            "disk usage, battery, volume, now playing, wifi, time, active app, translate, or git status."
        )

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
    if re.search(r'\bvolume\s+(up|down)\b', q):
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
        r'\bgit\s+diff\b',
        r'\bgit\s+log\b',
        r'\bgit\s+branches\b',
        r'\bwhat (?:has )?changed since (?:the )?last commit\b',
        r'\b(battery|battery\s+health|maximum\s+capacity|cycle\s+count|charging|power adapter)\b',
        r'\b(volume level|current volume|sound level|mute status)\b',
        r'\bset\s+(?:the\s+)?volume\s+(?:to|at)\s+\d+\b',
        r'\b(mute (?:my )?(?:volume|sound|audio)|unmute (?:my )?(?:volume|sound|audio)|turn (?:the )?sound (?:on|off))\b',
        r'\b(now playing|what song|what.?s.*playing|song.*playing|currently(?:\s+being)?\s+played|currently.*playing|current song|being played)\b',
        r'\b(wi[- ]?fi|ssid|network name|network am i on|what network|internet(?:\s+connection)?|connected to (?:the )?internet|am i online)\b',
        r'\b(what time|date today|active app|frontmost app|what app is active|which app is running|currently running app)\b',
        r'^\s*translate\b',
        r'^\s*say this in\b',
        r'\bsearch\s+for\s+.+\s+in\s+.+',
        r'\b(quit|close)\b.*\b(chrome|browser|safari|firefox|spotify|music|slack|discord|finder|notes|calendar|mail|figma|xcode|pycharm|calculator|settings|activity monitor|photos|messages|facetime|whatsapp|notion|zoom|teams|obsidian|arc)\b',
        r'\b(focus|activate|switch to)\b.*\b(chrome|browser|safari|firefox|spotify|music|slack|discord|finder|notes|calendar|mail|figma|xcode|pycharm|calculator|settings|activity monitor|photos|messages|facetime|whatsapp|notion|zoom|teams|obsidian|arc)\b',
        r'\bopen\s+url\s+\S+',
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
    if CLASSIFIER_MODE != "llm":
        return "QUESTION"

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


def _deterministic_intent_layer(text: str) -> str | None:
    if _build_mission_plan(text) is not None or _build_action_request(text) is not None:
        return handle_shell(text)
    return None


def _truth_policy_guard(text: str) -> str | None:
    if RESPONSE_STYLE != "truth_concise":
        return None
    q = text.lower()
    if re.search(r"\b(monitor|monitoring|cpu|ram|memory|service status|system status|any news)\b", q):
        return "I couldn't verify live system status from that request. Ask a specific command like battery, volume, song, wifi, time, or active app."
    return None


def _quick_truth_response(text: str) -> str | None:
    q = text.lower().strip()
    if not q:
        return "I didn't catch that."
    if re.search(r"\b(how are you|how you doing)\b", q):
        return "Ready and listening."
    if re.search(r"\b(thank you|thanks)\b", q):
        return "You're welcome."
    if re.search(r"\b(what can you do|help me|help)\b", q):
        return "I can handle battery, volume, now playing, wifi, time, active app, translate, and safe file actions."
    if re.search(r"\b(are you there|can you hear me)\b", q):
        return "I'm here."
    if re.search(r"\b(jarvis doctor|doctor jarvis|health check|diagnose jarvis)\b", q):
        return (
            "For mic issues, open System Settings, then Privacy and Microphone, and allow Terminal. "
            "If the hotkey does nothing, add Terminal to Accessibility. "
            "You can also run the status script in this folder from Terminal for a quick health check."
        )
    return None


# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
def route(text: str) -> str:
    if not text.strip():
        return "I didn't catch that."
    if re.search(r"\b(wake up|are you there|hello jarvis|hey jarvis)\b", text.lower()):
        return "I'm here and ready."
    pending_control = _handle_pending_mission_control(text)
    if pending_control is not None:
        return pending_control

    deterministic = _deterministic_intent_layer(text)
    if deterministic is not None:
        return deterministic
    quick = _quick_truth_response(text)
    if quick is not None:
        return quick

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
    guarded = _truth_policy_guard(text)
    if guarded is not None:
        return guarded
    if intent == "QUESTION" and CLASSIFIER_MODE != "llm" and RESPONSE_STYLE == "truth_concise":
        return "Ask a direct command and I will run it fast: battery, volume, now playing, wifi, time, active app, translate, open app, or music controls."
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
        self._last_interrupt_notice: float = 0.0
        self._stop_event          = threading.Event()
        self._wake_engine: WakeWordEngine | None = None
        self._wake_thread: threading.Thread | None = None
        self._init_mic()
        self._init_trigger_mode()

    def _init_mic(self):
        global _global_mic
        try:
            self._smart_mic = SmartMic()
            _global_mic = self._smart_mic
            backend_name = getattr(self._smart_mic, "_stt_mode", STT_BACKEND)
            if backend_name == "apple_native":
                print("✅ Smart mic ready (Apple Speech)")
            else:
                print("✅ Smart mic ready (WebRTC VAD)")
        except Exception as e:
            print(f"⚠️  Mic init error: {e}")
            print("   Grant mic access: System Settings → Privacy → Microphone")

    def _init_trigger_mode(self):
        if TRIGGER_MODE in {"wake", "hybrid"} and self._smart_mic:
            if getattr(self._smart_mic, "_stt_mode", "") == "apple_native" and WAKEWORD_BACKEND == "stt_phrase":
                print("⚠️  Wake backend stt_phrase + apple_native STT can feel slow. Use hotkey mode for best speed.")
            stt_phrase_engine = STTPhraseWakeWordEngine(self._smart_mic)
            if WAKEWORD_BACKEND == "openwakeword":
                self._wake_engine = OpenWakeWordEngine(fallback=stt_phrase_engine)
            else:
                self._wake_engine = stt_phrase_engine
            self._wake_thread = threading.Thread(target=self._wake_loop, daemon=True)
            self._wake_thread.start()
            print(f"✅ Wake-word mode active ({WAKEWORD_BACKEND})")

    def _wake_loop(self):
        if not self._wake_engine:
            return
        while not self._stop_event.is_set():
            if self._busy.locked():
                time.sleep(0.1)
                continue
            try:
                hit = self._wake_engine.wait_for_wake()
                if hit:
                    self.activate()
            except Exception as exc:
                print(f"⚠️  Wake-word loop error: {exc}")
                time.sleep(0.2)

    # ── Hotkey (pynput Listener — avoids Python 3.14 GlobalHotKeys crash) ──
    def _on_press(self, key):
        if TRIGGER_MODE not in {"hotkey", "hybrid"}:
            return
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
            now = time.monotonic()
            if now - self._last_interrupt_notice > 1.0:
                stop_speaking()
                print("⏳ Interrupted — press again to speak.")
                try:
                    speak("Interrupted. Press again to speak.")
                except Exception as exc:
                    print(f"⚠️  TTS error during interrupt notice: {exc}")
                self._last_interrupt_notice = now
            return

        def _run():
            try:
                t0 = time.perf_counter()
                capture: dict[str, int] = {}
                transcript_to_response_ms: int | None = None
                had_text = False
                response: str | None = None
                try:
                    stop_speaking()
                    _play_listen_cue()
                    time.sleep(0.05)
                    if not self._smart_mic:
                        response = "Microphone unavailable."
                    else:
                        text = self._smart_mic.listen()
                        capture = getattr(self._smart_mic, "last_capture_info", {})
                        if capture:
                            _latency_metric("cue_to_speech_start", int(capture.get("cue_to_speech_start_ms", 0)))
                            _latency_metric("speech_end_to_transcript", int(capture.get("speech_end_to_transcript_ms", 0)))
                            if "speech_duration_ms" in capture:
                                _latency_metric("speech_duration", int(capture.get("speech_duration_ms", 0)))
                        if text:
                            had_text = True
                            t_transcript = time.perf_counter()
                            routed = route(text)
                            transcript_to_response_ms = int((time.perf_counter() - t_transcript) * 1000)
                            _latency_metric("transcript_to_response", transcript_to_response_ms)
                            if capture:
                                post_speech_ms = int(capture.get("speech_end_to_transcript_ms", 0)) + transcript_to_response_ms
                                _latency_metric("post_speech_to_response", post_speech_ms)
                            response = routed
                        else:
                            _metric("turn.transcript_empty", 1, {})
                            response = "I didn't catch that."
                except Exception as exc:
                    print(f"⚠️  Unexpected error during turn: {exc}")
                    response = "Something went wrong with that request."
                if response:
                    try:
                        speak(response)
                    except Exception as exc:
                        print(f"⚠️  TTS error when speaking response: {exc}")
                total_ms = int((time.perf_counter() - t0) * 1000)
                _latency_metric("roundtrip_total", total_ms)
                _print_turn_timers(
                    capture,
                    transcript_to_response_ms=transcript_to_response_ms,
                    total_ms=total_ms,
                    had_text=had_text,
                )
            finally:
                self._busy.release()
                print("🔇 Ready.\n")

        threading.Thread(target=_run, daemon=True).start()

    def shutdown(self):
        self._stop_event.set()
        if self._wake_engine:
            try:
                self._wake_engine.close()
            except Exception:
                pass
        if self._smart_mic:
            try:
                self._smart_mic.close()
            except Exception:
                pass


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
    print(f"  Trigger: {TRIGGER_MODE}")
    print("  Hotkey : Command + Shift + J")
    print("  Quit   : Ctrl + C")
    print("=" * 52)

    _start_ollama()

    jarvis = Jarvis()

    if TRIGGER_MODE in {"hotkey", "hybrid"}:
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
        except Exception as e:
            print(f"❌ Hotkey registration failed: {e}")
            print("   Fix: System Settings → Privacy & Security → Accessibility")
            print("        Add Terminal and re-run.")
            if TRIGGER_MODE == "hotkey":
                sys.exit(1)
    if TRIGGER_MODE in {"wake", "hybrid"}:
        print("✅ Wake-word listening is active.")
    if TRIGGER_MODE == "hotkey":
        speak("Jarvis online. Press Command Shift J and speak.")
    elif TRIGGER_MODE == "wake":
        speak("Jarvis online. Say hey Jarvis to start.")
    else:
        speak("Jarvis online. Say hey Jarvis, or press Command Shift J.")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n🛑 Jarvis shutting down.")
        jarvis.shutdown()
        speak("Going offline.")
        sys.exit(0)


if __name__ == "__main__":
    main()
