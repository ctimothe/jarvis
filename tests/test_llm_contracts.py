from __future__ import annotations

import importlib
import types


def _install_stubs() -> None:
    # Minimal stubs so jarvis_clean imports without real network/audio.
    requests_mod = types.ModuleType("requests")
    requests_mod.exceptions = types.SimpleNamespace(Timeout=Exception)
    requests_mod.get = lambda *args, **kwargs: types.SimpleNamespace(status_code=503)
    requests_mod.post = lambda *args, **kwargs: types.SimpleNamespace(
        status_code=503, json=lambda: {"message": {"content": ""}}
    )

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

    import sys

    sys.modules["requests"] = requests_mod
    sys.modules["speech_recognition"] = sr_mod
    sys.modules["pyaudio"] = pyaudio_mod
    sys.modules["webrtcvad"] = webrtcvad_mod
    sys.modules["pynput"] = pynput_mod


def test_ask_ai_uses_truth_concise_prompt(monkeypatch):
    _install_stubs()
    jarvis = importlib.import_module("jarvis_clean")
    jarvis = importlib.reload(jarvis)

    monkeypatch.setattr(jarvis, "_ollama_alive", lambda: True)
    monkeypatch.setattr(jarvis, "RESPONSE_STYLE", "truth_concise")

    captured: dict[str, str] = {}

    def _fake_chat(system: str, user: str, temperature: float = 0.3, stop=None, timeout: int = 40) -> str:
        captured["system"] = system
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(jarvis, "_chat", _fake_chat)

    result = jarvis.ask_ai("hello")
    assert result == "ok"
    assert captured["system"] == jarvis.TRUTH_CONCISE_SYSTEM_PROMPT
    assert "You are J.A.R.V.I.S." in captured["system"]
    assert "cannot perform actions on the computer" in captured["system"]


def test_ask_ai_uses_balanced_prompt(monkeypatch):
    _install_stubs()
    jarvis = importlib.import_module("jarvis_clean")
    jarvis = importlib.reload(jarvis)

    monkeypatch.setattr(jarvis, "_ollama_alive", lambda: True)
    monkeypatch.setattr(jarvis, "RESPONSE_STYLE", "balanced")

    captured: dict[str, str] = {}

    def _fake_chat(system: str, user: str, temperature: float = 0.3, stop=None, timeout: int = 40) -> str:
        captured["system"] = system
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(jarvis, "_chat", _fake_chat)

    result = jarvis.ask_ai("hello")
    assert result == "ok"
    assert captured["system"] == jarvis.BALANCED_SYSTEM_PROMPT
    assert "You are J.A.R.V.I.S." in captured["system"]
    assert "cannot perform actions on the computer" in captured["system"]


def test_summary_prompt_used_for_action_output(monkeypatch):
    _install_stubs()
    jarvis = importlib.import_module("jarvis_clean")
    jarvis = importlib.reload(jarvis)

    captured: dict[str, str] = {}

    def _fake_chat(system: str, user: str, temperature: float = 0.3, stop=None, timeout: int = 40) -> str:
        captured["system"] = system
        captured["user"] = user
        return "summary"

    monkeypatch.setattr(jarvis, "_chat", _fake_chat)

    result = jarvis._format_action_result(
        jarvis.ActionResult(
            ok=True,
            return_code=0,
            stdout="line1\n" * 400,  # long output to force summarisation
            stderr="",
            duration_ms=10,
            command_repr="git status",
        )
    )
    assert result == "summary"
    assert captured["system"] == jarvis.SUMMARY_SYSTEM_PROMPT
    assert "Summarize this command output" in captured["system"]

