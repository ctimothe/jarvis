"""System status actions (battery, volume, wifi, etc.)."""

import subprocess
import time
import re
import datetime

from jarvis.actions.base import Action
from jarvis.types import ActionRequest, ActionResult
from jarvis import constants


def _run_safe_process(args: list[str], timeout: int = 10) -> ActionResult:
    """Run a subprocess safely."""
    started = time.time()
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(
            ok=result.returncode == 0,
            return_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            duration_ms=duration_ms,
            command_repr=" ".join(args),
        )
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        return ActionResult(False, -1, "", str(exc), duration_ms, " ".join(args))


def _osascript(script: str) -> ActionResult:
    """Run osascript."""
    return _run_safe_process(["osascript", "-e", script])


class BatteryStatusAction(Action):
    name = constants.ACTION_BATTERY_STATUS
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
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
                duration_ms=batt.duration_ms + profiler.duration_ms,
                command_repr="pmset -g batt && system_profiler SPPowerDataType",
            )
        return ActionResult(False, 1, "", "Unable to read battery details.", 0, "battery")

    def describe(self, request: ActionRequest) -> str:
        return "check battery status and health"


def _extract_battery_summary(pmset_output: str, profiler_output: str) -> str:
    parts = []
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

    health_bits = []
    if capacity_match:
        health_bits.append(f"maximum capacity {capacity_match.group(1)} percent")
    if cycle_match:
        health_bits.append(f"cycle count {cycle_match.group(1)}")
    if condition_match:
        health_bits.append(f"condition {condition_match.group(1).strip().lower()}")
    if health_bits:
        parts.append("Battery health: " + ", ".join(health_bits) + ".")

    return " ".join(parts).strip()


class VolumeStatusAction(Action):
    name = constants.ACTION_VOLUME_STATUS
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        script = 'output volume of (get volume settings) & "|" & output muted of (get volume settings)'
        result = _osascript(script)
        if result.ok and result.stdout:
            try:
                volume_raw, muted_raw = result.stdout.split("|", maxsplit=1)
                volume = volume_raw.strip()
                muted = muted_raw.strip().lower() == "true"
                summary = f"Output volume is {volume} percent. {'Muted.' if muted else 'Not muted.'}"
                return ActionResult(True, 0, summary, "", result.duration_ms, result.command_repr)
            except Exception:
                pass
        return result

    def describe(self, request: ActionRequest) -> str:
        return "check output volume"


class SetVolumeAction(Action):
    name = constants.ACTION_SET_VOLUME_LEVEL
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        level = request.args.get("level", 50)
        script = f'set volume output volume {level}'
        result = _osascript(script)
        summary = f"Output volume set to {level} percent."
        return ActionResult(
            ok=result.ok,
            return_code=result.return_code,
            stdout=summary if result.ok else "",
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            command_repr=script,
        )

    def describe(self, request: ActionRequest) -> str:
        return f"set volume to {request.args.get('level', 0)} percent"


class ToggleMuteAction(Action):
    name = constants.ACTION_TOGGLE_MUTE
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        mute = request.args.get("mute", True)
        script = f"set volume output muted {'true' if mute else 'false'}"
        result = _osascript(script)
        summary = "Output muted." if mute else "Output unmuted."
        return ActionResult(
            ok=result.ok,
            return_code=result.return_code,
            stdout=summary if result.ok else "",
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            command_repr=script,
        )

    def describe(self, request: ActionRequest) -> str:
        return "mute volume" if request.args.get("mute", True) else "unmute volume"


class NowPlayingAction(Action):
    name = constants.ACTION_NOW_PLAYING
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        spotify_script = (
            'try\n'
            'tell application "Spotify" to if player state is playing then return name of current track & " by " & artist of current track\n'
            'end try'
        )
        spotify = _osascript(spotify_script)
        if spotify.ok and spotify.stdout:
            return ActionResult(True, 0, f"Now playing: {spotify.stdout}.", "", spotify.duration_ms, spotify.command_repr)

        music_script = (
            'try\n'
            'tell application "Music" to if player state is playing then return name of current track & " by " & artist of current track\n'
            'end try'
        )
        music = _osascript(music_script)
        if music.ok and music.stdout:
            return ActionResult(True, 0, f"Now playing: {music.stdout}.", "", music.duration_ms, music.command_repr)

        return ActionResult(False, 1, "", "Could not verify a currently playing song.", 0, "now-playing")

    def describe(self, request: ActionRequest) -> str:
        return "check current song"


class WifiStatusAction(Action):
    name = constants.ACTION_WIFI_STATUS
    category = "system"
    requires_approval = False
    is_destructive = False

    def _detect_wifi_device(self) -> str:
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

    def execute(self, request: ActionRequest) -> ActionResult:
        device = self._detect_wifi_device()
        status = _run_safe_process(["networksetup", "-getairportnetwork", device], timeout=8)
        if status.ok and status.stdout:
            line = status.stdout.strip()
            if "Current Wi-Fi Network" in line:
                ssid = line.split(":", maxsplit=1)[1].strip()
                summary = f"Wi-Fi is connected to {ssid}."
            else:
                summary = f"Wi-Fi status: {line}."
            return ActionResult(True, 0, summary, "", status.duration_ms, status.command_repr)
        return ActionResult(False, 1, "", "Could not verify Wi-Fi status.", status.duration_ms, status.command_repr)

    def describe(self, request: ActionRequest) -> str:
        return "check wifi status"


class TimeStatusAction(Action):
    name = constants.ACTION_TIME_STATUS
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        now = datetime.datetime.now()
        return ActionResult(
            ok=True,
            return_code=0,
            stdout=now.strftime("It is %I:%M %p on %A, %B %d, %Y."),
            stderr="",
            duration_ms=1,
            command_repr="local datetime",
        )

    def describe(self, request: ActionRequest) -> str:
        return "check current date and time"


class ActiveAppAction(Action):
    name = constants.ACTION_ACTIVE_APP
    category = "system"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        script = 'tell application "System Events" to get name of first process whose frontmost is true'
        result = _osascript(script)
        if result.ok and result.stdout:
            return ActionResult(True, 0, f"Active app is {result.stdout}.", "", result.duration_ms, result.command_repr)
        return ActionResult(False, 1, "", "Could not verify active app.", result.duration_ms, result.command_repr)

    def describe(self, request: ActionRequest) -> str:
        return "check active app"


class TranslateTextAction(Action):
    name = constants.ACTION_TRANSLATE_TEXT
    category = "language"
    requires_approval = False
    is_destructive = False

    def execute(self, request: ActionRequest) -> ActionResult:
        from jarvis.llm.registry import get_llm_registry
        source_text = request.args.get("text", "")
        source_lang = request.args.get("source_lang", "english")
        target_lang = request.args.get("target_lang", "spanish")

        if not source_text:
            return ActionResult(False, 1, "", "Missing text to translate.", 0, "translate")

        llm = get_llm_registry().get_backend()
        if llm and llm.is_available():
            prompt = f"Translate from {source_lang} to {target_lang}: {source_text}"
            result = llm.complete(prompt)
            return ActionResult(True, 0, f"In {target_lang}: {result}", "", 0, f"translate {source_lang}->{target_lang}")

        return ActionResult(False, 1, "", "Translation unavailable.", 0, "translate")

    def describe(self, request: ActionRequest) -> str:
        return f"translate text to {request.args.get('target_lang', 'spanish')}"