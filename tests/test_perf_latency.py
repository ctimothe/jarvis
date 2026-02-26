from __future__ import annotations

import importlib
import statistics
import sys
import time
import types


def _install_stubs() -> None:
    requests_mod = types.ModuleType("requests")
    requests_mod.exceptions = types.SimpleNamespace(Timeout=Exception)
    requests_mod.get = lambda *args, **kwargs: types.SimpleNamespace(status_code=503)
    requests_mod.post = lambda *args, **kwargs: types.SimpleNamespace(status_code=503, json=lambda: {})

    sr_mod = types.ModuleType("speech_recognition")
    sr_mod.Recognizer = type("Recognizer", (), {"recognize_google": lambda self, *a, **k: ""})
    sr_mod.AudioData = type("AudioData", (), {"__init__": lambda self, *a, **k: None})
    sr_mod.UnknownValueError = Exception
    sr_mod.RequestError = Exception

    pyaudio_mod = types.ModuleType("pyaudio")
    pyaudio_mod.PyAudio = type("PyAudio", (), {"open": lambda self, *a, **k: None})
    pyaudio_mod.paInt16 = 8

    webrtcvad_mod = types.ModuleType("webrtcvad")
    webrtcvad_mod.Vad = lambda *a, **k: type("Vad", (), {"is_speech": lambda self, *x, **y: False})()

    keyboard_mod = types.ModuleType("keyboard")
    keyboard_mod.Key = types.SimpleNamespace(cmd=object(), cmd_l=object(), cmd_r=object(), shift=object(), shift_l=object(), shift_r=object())
    keyboard_mod.KeyCode = type("KeyCode", (), {})
    keyboard_mod.Listener = type("Listener", (), {"__init__": lambda self, *a, **k: None, "start": lambda self: None})

    pynput_mod = types.ModuleType("pynput")
    pynput_mod.keyboard = keyboard_mod

    sys.modules["requests"] = requests_mod
    sys.modules["speech_recognition"] = sr_mod
    sys.modules["pyaudio"] = pyaudio_mod
    sys.modules["webrtcvad"] = webrtcvad_mod
    sys.modules["pynput"] = pynput_mod


def test_latency_budget_for_local_status_path(monkeypatch):
    _install_stubs()
    jarvis = importlib.import_module("jarvis_clean")
    jarvis = importlib.reload(jarvis)

    monkeypatch.setattr(jarvis, "handle_shell", lambda _text: "ok")

    runs_ms: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        result = jarvis.route("is my laptop charging")
        runs_ms.append((time.perf_counter() - t0) * 1000)
        assert result == "ok"

    p50 = statistics.median(runs_ms)
    p90 = sorted(runs_ms)[int(len(runs_ms) * 0.9) - 1]

    assert p50 <= 1200
    assert p90 <= 2000
