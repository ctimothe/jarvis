from __future__ import annotations

import importlib
import sys
import types

import pytest


def _install_dependency_stubs() -> None:
    requests_mod = types.ModuleType("requests")

    class _Timeout(Exception):
        pass

    requests_mod.exceptions = types.SimpleNamespace(Timeout=_Timeout)
    requests_mod.get = lambda *args, **kwargs: types.SimpleNamespace(status_code=503)
    requests_mod.post = lambda *args, **kwargs: types.SimpleNamespace(status_code=503, json=lambda: {})

    sr_mod = types.ModuleType("speech_recognition")

    class _Recognizer:
        def recognize_google(self, *args, **kwargs):
            return ""

    class _AudioData:
        def __init__(self, *args, **kwargs):
            pass

    class _UnknownValueError(Exception):
        pass

    class _RequestError(Exception):
        pass

    sr_mod.Recognizer = _Recognizer
    sr_mod.AudioData = _AudioData
    sr_mod.UnknownValueError = _UnknownValueError
    sr_mod.RequestError = _RequestError

    pyaudio_mod = types.ModuleType("pyaudio")

    class _PyAudio:
        def open(self, *args, **kwargs):
            raise RuntimeError("audio disabled for tests")

    pyaudio_mod.PyAudio = _PyAudio
    pyaudio_mod.paInt16 = 8

    webrtcvad_mod = types.ModuleType("webrtcvad")

    class _Vad:
        def __init__(self, *args, **kwargs):
            pass

        def is_speech(self, *args, **kwargs):
            return False

    webrtcvad_mod.Vad = _Vad

    keyboard_mod = types.ModuleType("keyboard")
    keyboard_mod.Key = types.SimpleNamespace(
        cmd=object(),
        cmd_l=object(),
        cmd_r=object(),
        shift=object(),
        shift_l=object(),
        shift_r=object(),
    )

    class _KeyCode:
        def __init__(self, char: str | None = None):
            self.char = char

    class _Listener:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            return None

    keyboard_mod.KeyCode = _KeyCode
    keyboard_mod.Listener = _Listener

    pynput_mod = types.ModuleType("pynput")
    pynput_mod.keyboard = keyboard_mod

    sys.modules["requests"] = requests_mod
    sys.modules["speech_recognition"] = sr_mod
    sys.modules["pyaudio"] = pyaudio_mod
    sys.modules["webrtcvad"] = webrtcvad_mod
    sys.modules["pynput"] = pynput_mod


@pytest.fixture()
def jarvis(monkeypatch):
    _install_dependency_stubs()
    module = importlib.import_module("jarvis_clean")
    module = importlib.reload(module)

    monkeypatch.setattr(module, "HOME", "/Users/tester")
    monkeypatch.setattr(module, "_rate_limiter", module.FixedWindowRateLimiter(max_per_minute=9999))
    monkeypatch.setattr(module, "_pending_mission", None)
    monkeypatch.setattr(module, "_last_mission_report", "No mission has run yet.")
    return module


def test_build_create_folder_request(jarvis):
    request = jarvis._build_action_request("create folder called demo")

    assert request is not None
    assert request.action == jarvis.ACTION_CREATE_FOLDER
    assert request.args["path"] == "/Users/tester/demo"


def test_build_find_request(jarvis):
    request = jarvis._build_action_request("find report.txt in documents")

    assert request is not None
    assert request.action == jarvis.ACTION_FIND_NAME
    assert request.args["pattern"] == "report.txt"
    assert request.args["path"] == "/Users/tester/documents"


def test_build_battery_request(jarvis):
    request = jarvis._build_action_request("what is the percentage of my battery health")

    assert request is not None
    assert request.action == jarvis.ACTION_BATTERY_STATUS


@pytest.mark.parametrize(
    ("query", "expected_action"),
    [
        ("what is my volume level", "ACTION_VOLUME_STATUS"),
        ("what song is playing", "ACTION_NOW_PLAYING"),
        ("am i on wifi", "ACTION_WIFI_STATUS"),
        ("what time is it", "ACTION_TIME_STATUS"),
        ("what app is active", "ACTION_ACTIVE_APP"),
        ('translate "hello" to spanish', "ACTION_TRANSLATE_TEXT"),
    ],
)
def test_build_new_status_requests(jarvis, query, expected_action):
    request = jarvis._build_action_request(query)
    assert request is not None
    assert request.action == getattr(jarvis, expected_action)


def test_parse_translation_default_target(jarvis):
    request = jarvis._build_action_request("translate hello")
    assert request is not None
    assert request.action == jarvis.ACTION_TRANSLATE_TEXT
    assert request.args["target_lang"] == jarvis.TRANSLATION_DEFAULT_TARGET


def test_policy_blocks_protected_paths(jarvis):
    request = jarvis.ActionRequest(
        action=jarvis.ACTION_LIST_PATH,
        args={"path": "/System/Library"},
        principal="tester",
        reason="test",
    )

    decision = jarvis._policy_check(request)

    assert decision.allowed is False
    assert "protected path blocked" in decision.reason


def test_policy_blocks_write_outside_home(jarvis):
    request = jarvis.ActionRequest(
        action=jarvis.ACTION_CREATE_FILE,
        args={"path": "/tmp/demo.txt"},
        principal="tester",
        reason="test",
    )

    decision = jarvis._policy_check(request)

    assert decision.allowed is False
    assert "outside home blocked" in decision.reason


def test_policy_requires_approval_for_delete(jarvis):
    request = jarvis.ActionRequest(
        action=jarvis.ACTION_DELETE_PATH,
        args={"path": "/Users/tester/demo.txt"},
        principal="tester",
        reason="test",
    )

    decision = jarvis._policy_check(request)

    assert decision.allowed is True
    assert decision.requires_approval is True


def test_build_mission_plan(jarvis):
    plan = jarvis._build_mission_plan("create folder called wow then create file called wow/notes.txt")

    assert plan is not None
    assert len(plan.requests) == 2
    assert plan.requests[0].action == jarvis.ACTION_CREATE_FOLDER
    assert plan.requests[0].args["path"] == "/Users/tester/wow"
    assert plan.requests[1].action == jarvis.ACTION_CREATE_FILE
    assert plan.requests[1].args["path"] == "/Users/tester/wow/notes.txt"


def test_pending_mission_execute_control(jarvis, monkeypatch):
    plan = jarvis._build_mission_plan("create folder called wow then list wow")
    assert plan is not None
    jarvis._set_pending_mission(plan)
    monkeypatch.setattr(jarvis, "_execute_mission_plan", lambda _plan: "mission executed")

    response = jarvis._handle_pending_mission_control("execute mission")

    assert response == "mission executed"
    assert jarvis._peek_pending_mission() is None


def test_pending_mission_cancel_control(jarvis):
    plan = jarvis._build_mission_plan("create folder called wow then list wow")
    assert plan is not None
    jarvis._set_pending_mission(plan)

    response = jarvis._handle_pending_mission_control("cancel mission")

    assert response == "Mission cancelled."
    assert jarvis._peek_pending_mission() is None


def test_classify_question_not_music(jarvis):
    intent = jarvis._classify("what's up with the service")
    assert intent == "QUESTION"


def test_classify_battery_as_shell(jarvis):
    intent = jarvis._classify("what is the percentage of my battery health")
    assert intent == "SHELL"


def test_classify_new_status_queries_as_shell(jarvis):
    assert jarvis._classify("what song is currently playing") == "SHELL"
    assert jarvis._classify("what app is active") == "SHELL"
    assert jarvis._classify("translate hello to spanish") == "SHELL"


def test_classify_pause_music_as_music(jarvis):
    intent = jarvis._classify("pause the music")
    assert intent == "MUSIC"


def test_route_structured_query_bypasses_classifier(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_classify", lambda _text: "MUSIC")
    monkeypatch.setattr(jarvis, "handle_shell", lambda _text: "shell handled")

    response = jarvis.route("what is the percentage of my battery health")

    assert response == "shell handled"


def test_deterministic_layer_handles_translation(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "handle_shell", lambda _text: "translated")
    response = jarvis.route("translate hello to spanish")
    assert response == "translated"


def test_extract_battery_summary(jarvis):
    pmset_output = "Now drawing from 'Battery Power'\\n -InternalBattery-0\\t81%; discharging; 4:10 remaining present: true\\n"
    profiler_output = "Cycle Count: 120\\nCondition: Normal\\nMaximum Capacity: 92%\\n"

    summary = jarvis._extract_battery_summary(pmset_output, profiler_output)

    assert "81 percent" in summary
    assert "maximum capacity 92 percent" in summary
    assert "cycle count 120" in summary


def test_run_volume_status_action_parsing(jarvis, monkeypatch):
    fake = jarvis.ActionResult(True, 0, "52|false", "", 10, "osascript")
    monkeypatch.setattr(jarvis, "_run_safe_process", lambda *args, **kwargs: fake)
    result = jarvis._run_volume_status_action()
    assert result.ok is True
    assert "52 percent" in result.stdout


def test_run_now_playing_action_fallback(jarvis, monkeypatch):
    spotify_empty = jarvis.ActionResult(False, 1, "", "not running", 8, "osascript spotify")
    music_playing = jarvis.ActionResult(True, 0, "Everlong by Foo Fighters", "", 8, "osascript music")
    calls = iter([spotify_empty, music_playing])
    monkeypatch.setattr(jarvis, "_run_safe_process", lambda *args, **kwargs: next(calls))
    result = jarvis._run_now_playing_action()
    assert result.ok is True
    assert "Everlong" in result.stdout


def test_run_wifi_status_action_parsing(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_detect_wifi_device", lambda: "en0")
    wifi_result = jarvis.ActionResult(True, 0, "Current Wi-Fi Network: MyWifi", "", 7, "networksetup")
    monkeypatch.setattr(jarvis, "_run_safe_process", lambda *args, **kwargs: wifi_result)
    result = jarvis._run_wifi_status_action()
    assert result.ok is True
    assert "MyWifi" in result.stdout


def test_local_dictionary_translation(jarvis):
    translated = jarvis._translate_text_local("hello", "spanish", "english")
    assert translated == "hola"


def test_truth_policy_guard(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "RESPONSE_STYLE", "truth_concise")
    response = jarvis.route("any news with system status")
    assert "couldn't verify" in response.lower()


def test_route_wake_up_short_response(jarvis):
    response = jarvis.route("wake up")
    assert response == "I'm here and ready."


@pytest.mark.parametrize(
    "query",
    [
        "is my laptop charging",
        "what is my volume level",
        "what song is playing",
        "what network am i on",
        "what app is active",
        "translate hello to spanish",
        "check battery health",
        "show disk usage",
        "git status in ~/code",
        "create folder called demo",
        "list files in ~/Documents",
        "find notes.txt in ~/Documents",
        "move ~/a to ~/b",
        "copy ~/a to ~/b",
        "rename ~/a to ~/b",
        "delete ~/tmp-file",
        "what time is it",
        "date today",
        "ssid status",
        "current song",
        "maximum capacity battery",
        "active app please",
        "translate good morning to french",
        "say this in spanish: hello",
        "wifi status",
        "volume status",
        "track playing",
        "time now",
        "frontmost app",
        "translate thank you",
    ],
)
def test_canonical_queries_hit_deterministic_layer(jarvis, monkeypatch, query):
    monkeypatch.setattr(jarvis, "handle_shell", lambda _text: "ok")
    response = jarvis.route(query)
    assert response == "ok"


def test_classify_rules_mode_skips_llm(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "CLASSIFIER_MODE", "rules")
    monkeypatch.setattr(jarvis, "_ollama_alive", lambda: True)
    monkeypatch.setattr(jarvis, "_chat", lambda **_kwargs: "MUSIC")

    assert jarvis._classify("this is ambiguous text") == "QUESTION"


def test_route_quick_truth_response(jarvis):
    response = jarvis.route("how are you jarvis")
    assert response == "Ready and listening."


def test_stt_wakeword_phrase_is_strict(jarvis):
    class _FakeMic:
        def __init__(self, heard: str):
            self._heard = heard

        def listen(self, **_kwargs):
            return self._heard

    engine = jarvis.STTPhraseWakeWordEngine(_FakeMic("jarvis online say hey jarvis"))
    assert engine.wait_for_wake() is False

    engine_ok = jarvis.STTPhraseWakeWordEngine(_FakeMic("hey jarvis"))
    assert engine_ok.wait_for_wake() is True
