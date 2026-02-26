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


def test_classify_pause_music_as_music(jarvis):
    intent = jarvis._classify("pause the music")
    assert intent == "MUSIC"


def test_route_structured_query_bypasses_classifier(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_classify", lambda _text: "MUSIC")
    monkeypatch.setattr(jarvis, "handle_shell", lambda _text: "shell handled")

    response = jarvis.route("what is the percentage of my battery health")

    assert response == "shell handled"


def test_extract_battery_summary(jarvis):
    pmset_output = "Now drawing from 'Battery Power'\\n -InternalBattery-0\\t81%; discharging; 4:10 remaining present: true\\n"
    profiler_output = "Cycle Count: 120\\nCondition: Normal\\nMaximum Capacity: 92%\\n"

    summary = jarvis._extract_battery_summary(pmset_output, profiler_output)

    assert "81 percent" in summary
    assert "maximum capacity 92 percent" in summary
    assert "cycle count 120" in summary


def test_route_wake_up_short_response(jarvis):
    response = jarvis.route("wake up")
    assert response == "I'm here and ready."
