"""TTS backend base protocol."""

from abc import ABC, abstractmethod


class TTSBackend(ABC):
    """Base class for text-to-speech backends."""

    name: str = ""

    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak the given text."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
        pass

    def stop(self) -> None:
        """Stop speaking. Override in subclasses."""
        pass


class NullTTSBackend(TTSBackend):
    """Null TTS that does nothing."""

    name = "null"

    def speak(self, text: str) -> None:
        pass

    def is_available(self) -> bool:
        return True


class MacOSTTSBackend(TTSBackend):
    """macOS TTS using the 'say' command."""

    name = "macos"

    def __init__(self, rate: int = 185):
        self.rate = rate

    def speak(self, text: str) -> None:
        import subprocess
        subprocess.Popen(["say", "-r", str(self.rate), text])

    def is_available(self) -> bool:
        import shutil
        return shutil.which("say") is not None

    def stop(self) -> None:
        import subprocess
        subprocess.run(["pkill", "-f", "say"], capture_output=True)


class LinuxTTSBackend(TTSBackend):
    """Linux TTS using espeak-ng."""

    name = "espeak"

    def speak(self, text: str) -> None:
        import subprocess
        subprocess.Popen(["espeak", text])

    def is_available(self) -> bool:
        import shutil
        return shutil.which("espeak") is not None

    def stop(self) -> None:
        import subprocess
        subprocess.run(["pkill", "-f", "espeak"], capture_output=True)


class WindowsTTSBackend(TTSBackend):
    """Windows TTS using pyttsx3."""

    name = "pyttsx3"

    def __init__(self):
        self._engine = None

    def speak(self, text: str) -> None:
        try:
            import pyttsx3
            if self._engine is None:
                self._engine = pyttsx3.init()
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            pass

    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

    def stop(self) -> None:
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass