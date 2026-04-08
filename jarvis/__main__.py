"""CLI entry point for Jarvis."""

import argparse
import sys
import os

from jarvis.config import Config
from jarvis.core.router import Router
from jarvis.llm.registry import get_llm_registry


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis Open - Privacy-first voice assistant",
        prog="jarvis",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    run_parser = subparsers.add_parser("run", help="Run the voice assistant")
    run_parser.add_argument("--hotkey", action="store_true", help="Force hotkey mode")
    run_parser.add_argument("--wake", action="store_true", help="Force wake-word mode")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers.add_parser("doctor", help="Run health checks")

    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_parser.add_argument("action", choices=["show", "edit"], help="Config action")
    config_parser.add_argument("--file", help="Config file path")

    subparsers.add_parser("info", help="Show version and info")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "run":
        run_jarvis(args)
    elif args.command == "doctor":
        run_doctor()
    elif args.command == "config":
        run_config(args)
    elif args.command == "info":
        run_info()


def run_jarvis(args):
    config = Config.load()

    if args.hotkey:
        config.trigger.mode = "hotkey"
    elif args.wake:
        config.trigger.mode = "wake"

    print("=" * 52)
    print("  Jarvis Open  —  Voice Assistant")
    print("=" * 52)
    print(f"  LLM Backend: {config.llm.backend}")
    print(f"  STT Backend: {config.stt.backend}")
    print(f"  TTS Backend: {config.tts.backend}")
    print(f"  Trigger: {config.trigger.mode}")
    print("  Hotkey: Command + Shift + J")
    print("  Quit: Ctrl + C")
    print("=" * 52)

    router = Router(config)
    router.run()


def run_doctor():
    """Run health checks on all backends."""
    from jarvis.types import HealthStatus

    config = Config.load()

    print("🩺 Running Jarvis health checks...\n")

    results: list[HealthStatus] = []

    print("📡 Checking LLM backend...")
    from jarvis.llm.ollama import OllamaBackend
    llm = OllamaBackend(url=config.llm.url, model=config.llm.model)
    available = llm.is_available()
    results.append(HealthStatus(
        name="ollama",
        available=available,
        error_message=None if available else "Ollama not running",
        suggestions=["Run 'ollama serve' to start Ollama"] if not available else None,
    ))
    print(f"  {'✅' if available else '❌'} Ollama: {'available' if available else 'not available'}\n")

    print("📊 Checking STT backend...")
    stt_available = _check_stt(config)
    results.append(HealthStatus(
        name="stt",
        available=stt_available,
        error_message=None if stt_available else "No STT backend available",
        suggestions=["Install pyaudio, webrtcvad for local STT"] if not stt_available else None,
    ))
    print(f"  {'✅' if stt_available else '⚠️'} STT: {'available' if stt_available else 'limited'}\n")

    print("🔊 Checking TTS backend...")
    tts_available = _check_tts(config)
    results.append(HealthStatus(
        name="tts",
        available=tts_available,
        error_message=None if tts_available else "No TTS backend available",
    ))
    print(f"  {'✅' if tts_available else '⚠️'} TTS: {'available' if tts_available else 'limited'}\n")

    print("🔐 Checking policy engine...")
    from jarvis.policy.engine import PolicyEngine
    policy = PolicyEngine(config)
    print(f"  ✅ Policy engine loaded\n")

    print("📁 Checking configuration...")
    config_path = config.home_dir / ".jarvis" / "config.yaml"
    if config_path.exists():
        print(f"  ✅ Config file exists: {config_path}\n")
    else:
        print(f"  ℹ️  No config file yet (will use defaults)\n")
        print(f"     Create one with: jarvis config edit\n")

    print("\n" + "=" * 52)
    print("Summary:")
    for r in results:
        status = "✅" if r.available else "❌"
        print(f"  {status} {r.name}: {'OK' if r.available else r.error_message}")
        if r.suggestions:
            for s in r.suggestions:
                print(f"      → {s}")

    print("\nPrivacy settings:")
    print(f"  Audit logging: {'enabled' if config.privacy.audit_enabled else 'disabled (default)'}")
    print(f"  Metrics: {'enabled' if config.privacy.metrics_enabled else 'disabled (default)'}")


def _check_stt(config: Config) -> bool:
    """Check STT availability."""
    if config.stt.backend in ("apple", "auto") and config.is_macos:
        return True
    try:
        import pyaudio
        import webrtcvad
        return True
    except ImportError:
        return False


def _check_tts(config: Config) -> bool:
    """Check TTS availability."""
    if config.is_macos:
        return True
    try:
        import pyttsx3
        return True
    except ImportError:
        return False


def run_config(args):
    if args.action == "show":
        config = Config.load()
        import yaml
        print(yaml.dump(config.to_dict(), default_flow_style=False))
    elif args.action == "edit":
        config_path = args.file or (Config().home_dir / ".jarvis" / "config.yaml")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            os.system(f"{os.environ.get('EDITOR', 'nano')} {config_path}")
        else:
            print(f"Created new config at {config_path}")
            config = Config()
            config.save(config_path)


def run_info():
    print("Jarvis Open v2.0.0")
    print("Privacy-first, extensible voice assistant")
    print()
    print("Documentation: https://github.com/yourname/jarvis")
    print("License: MIT")


if __name__ == "__main__":
    main()