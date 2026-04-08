# Jarvis Open - Project Specification

**Version**: 2.0  
**Status**: Draft  
**Last Updated**: 2026-04-08

---

## 1. Vision & Philosophy

### 1.1 Purpose

**Jarvis Open** is a privacy-first, extensible voice assistant that runs locally on user's machine. It provides:

- **Voice control** of the local machine (file ops, system status, app control)
- **AI-powered conversation** via configurable LLM backends
- **Web dashboard** for configuration, logs, and monitoring
- **Bounded autonomy** — actions are typed, validated, and policy-controlled

### 1.2 Core Principles

| Principle | Description |
|-----------|-------------|
| **Local-first** | All data stays on user's machine by default |
| **Privacy-by-default** | No telemetry, no audit logs unless explicitly enabled |
| **Modular architecture** | Every component is replaceable via abstraction |
| **Fail gracefully** | Missing dependencies don't crash the app |
| **Open plugin model** | Anyone can extend with new actions, STT, TTS, LLMs |

### 1.3 Target Users

- Developers who want a CLI voice assistant
- Power users who value privacy and local control
- Tinkerers who want to extend functionality

---

## 2. Architecture Overview

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                        Jarvis Open                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Voice Input  │  │   Web UI    │  │    REST API          │  │
│  │  (STT)       │  │  (Dashboard)│  │  (External Control) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────┘  │
│         │                 │                      │            │
│         ▼                 ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     Router / Classifier                  │   │
│  │   (Determines: command type, action, parameters)        │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│         ┌────────────────────┼────────────────────┐            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐   │
│  │   Actions   │     │   AI/LLM    │     │  System Query   │   │
│  │ (filesystem,│     │ (conversation│     │ (battery, wifi)│   │
│  │  git, apps) │     │  completion)│     │                 │   │
│  └──────┬──────┘     └──────┬──────┘     └────────┬────────┘   │
│         │                   │                      │            │
│         ▼                   ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Policy Engine (security layer)              │   │
│  │  - Path restrictions  - Rate limiting  - Approval gates │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│                             ▼                                    │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐   │
│  │  Platform   │     │   TTS       │     │   LLM Backend   │   │
│  │  (mac/linux │     │ (say/espeak │     │ (ollama/openai/ │   │
│  │   /windows) │     │  /pyttsx3)  │     │   anthropic)    │   │
│  └─────────────┘     └─────────────┘     └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Layers

| Layer | Responsibility |
|-------|----------------|
| **Interface** | Voice (STT), Web, REST API |
| **Router** | Parse input → determine intent → route to handler |
| **Engine** | Execute actions, query system, call AI |
| **Policy** | Validate, rate-limit, require approval |
| **Backend** | Platform-specific (TTS, STT, system commands) |

---

## 3. Module Structure

### 3.1 Package Layout

```
jarvis/
├── __init__.py           # Public API: Jarvis(), run()
├── __main__.py           # CLI: jarvis run / jarvis doctor
├── config.py             # Configuration management
├── constants.py          # Action names, limits
├── types.py              # Dataclasses
│
├── core/
│   ├── __init__.py
│   ├── router.py         # Input → intent routing
│   ├── classifier.py    # Rule-based + LLM classifier
│   └── executor.py      # Action execution engine
│
├── actions/
│   ├── __init__.py
│   ├── base.py          # Action protocol (ABC)
│   ├── filesystem.py    # create, list, find, move, copy, delete
│   ├── git.py           # status, diff, log, branches
│   ├── apps.py          # open, quit, focus app
│   ├── system.py        # battery, volume, wifi, time
│   └── registry.py     # Action registration/discovery
│
├── policy/
│   ├── __init__.py
│   ├── engine.py        # Policy evaluation
│   ├── rate_limiter.py  # Rate limiting
│   ├── path_validator.py # Path restrictions
│   └── approver.py      # Destructive action approval
│
├── llm/
│   ├── __init__.py
│   ├── base.py          # LLMBackend protocol
│   ├── ollama.py        # Ollama implementation
│   ├── openai.py       # OpenAI implementation
│   ├── anthropic.py    # Anthropic implementation
│   ├── registry.py     # LLM backend registry
│   └── prompt.py       # System prompts, templates
│
├── stt/
│   ├── __init__.py
│   ├── base.py         # STTBackend protocol
│   ├── vad.py          # WebRTC VAD wrapper
│   ├── apple.py        # Apple Speech (macOS)
│   ├── whisper.py      # Faster-Whisper local
│   ├── google.py      # Google STT
│   └── registry.py    # STT backend registry
│
├── tts/
│   ├── __init__.py
│   ├── base.py        # TTSBackend protocol
│   ├── macos.py       # say command
│   ├── espeak.py      # espeak-ng (Linux)
│   ├── pyttsx3.py     # Windows TTS
│   └── registry.py   # TTS backend registry
│
├── system/
│   ├── __init__.py
│   ├── base.py        # SystemBackend protocol
│   ├── macos.py       # macOS implementations
│   ├── linux.py       # Linux implementations
│   └── windows.py     # Windows implementations
│
├── audit/
│   ├── __init__.py
│   └── logger.py      # Audit + metrics (opt-in)
│
├── plugins/
│   ├── __init__.py
│   ├── loader.py      # Plugin discovery & loading
│   └── base.py        # Plugin protocol
│
└── web/
    ├── __init__.py
    ├── app.py         # Flask/FastAPI app
    ├── routes.py     # API routes
    ├── static/       # Dashboard assets
    └── templates/    # HTML templates
```

---

## 4. Configuration

### 4.1 Configuration Sources (Priority Order)

1. **Environment variables** (highest) — `JARVIS_*`
2. **Config file** — `~/.jarvis/config.yaml`
3. **Defaults** — hardcoded sensible defaults

### 4.2 Key Configuration

```yaml
# ~/.jarvis/config.yaml
jarvis:
  # Voice trigger
  trigger_mode: "hotkey"  # hotkey | wake | hybrid
  
  # STT (Speech-to-Text)
  stt:
    backend: "auto"      # apple | whisper | google | auto
    model: "tiny.en"     # whisper model
    vad_aggression: 2     # 0-3 (WebRTC)
  
  # TTS (Text-to-Speech)
  tts:
    backend: "auto"       # macos | espeak | pyttsx3 | auto
    rate: 185             # words per minute
  
  # AI/LLM
  llm:
    backend: "ollama"     # ollama | openai | anthropic | none
    model: "llama3.1:8b"  # model name
    temperature: 0.3
    fallback_response: "AI is offline."
  
  # Privacy
  privacy:
    audit_enabled: false  # OFF by default
    metrics_enabled: false
  
  # Network
  network:
    allowed_hosts: ["localhost", "192.168.*"]
    allowed_ports: [80, 443, 8080]
  
  # Security
  security:
    require_approval_for_destructive: true
    rate_limit_per_minute: 20
    max_action_timeout_seconds: 20
```

### 4.3 Environment Variable Mapping

| Env Var | Config Path | Type | Default |
|---------|-------------|------|---------|
| `JARVIS_TRIGGER_MODE` | trigger_mode | str | "hotkey" |
| `JARVIS_STT_BACKEND` | stt.backend | str | "auto" |
| `JARVIS_TTS_BACKEND` | tts.backend | str | "auto" |
| `JARVIS_LLM_BACKEND` | llm.backend | str | "ollama" |
| `JARVIS_LLM_MODEL` | llm.model | str | "llama3.1:8b" |
| `JARVIS_AUDIT` | privacy.audit_enabled | bool | false |
| `JARVIS_METRICS` | privacy.metrics_enabled | bool | false |
| `JARVIS_WEB_PORT` | web.port | int | 8080 |
| `JARVIS_WEB_PASSWORD` | web.password | str | (none) |

---

## 5. Action System

### 5.1 Action Protocol

```python
# jarvis/actions/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ActionRequest:
    action: str
    args: dict[str, Any]
    principal: str
    reason: str
    
@dataclass  
class ActionResult:
    ok: bool
    stdout: str
    stderr: str
    duration_ms: int

class Action(ABC):
    name: str
    category: str       # fs, git, system, apps, ai
    requires_approval: bool = False
    is_destructive: bool = False
    
    @abstractmethod
    def execute(self, request: ActionRequest) -> ActionResult: ...
    
    def validate_args(self, args: dict) -> bool: ...
    def describe(self, request: ActionRequest) -> str: ...
```

### 5.2 Built-in Actions

| Action | Category | Destructive | Approval Required |
|--------|----------|-------------|-------------------|
| `create_folder` | fs | No | No |
| `create_file` | fs | No | No |
| `list_path` | fs | No | No |
| `find_name` | fs | No | No |
| `move_path` | fs | No | No |
| `copy_path` | fs | No | No |
| `rename_path` | fs | No | No |
| `delete_path` | fs | **Yes** | **Yes** |
| `git_status` | git | No | No |
| `git_diff` | git | No | No |
| `git_log` | git | No | No |
| `git_branches` | git | No | No |
| `open_app` | apps | No | No |
| `quit_app` | apps | No | No |
| `focus_app` | apps | No | No |
| `battery_status` | system | No | No |
| `volume_status` | system | No | No |
| `volume_set` | system | No | No |
| `mute_toggle` | system | No | No |
| `now_playing` | system | No | No |
| `wifi_status` | system | No | No |
| `time_status` | system | No | No |
| `active_app` | system | No | No |
| `translate_text` | system | No | No |
| `open_url` | apps | No | No |

### 5.3 Plugin Actions

Users can add custom actions by:

```python
# ~/.jarvis/plugins/my_action.py
from jarvis.actions.base import Action, ActionRequest, ActionResult

class MyCustomAction(Action):
    name = "my_custom_action"
    category = "custom"
    
    def execute(self, request: ActionRequest) -> ActionResult:
        # implementation
        return ActionResult(ok=True, stdout="Done", stderr="", duration_ms=10)

# Auto-discovered via plugin loader
```

---

## 6. Policy Engine

### 6.1 Policy Types

| Policy | Description | Default |
|--------|-------------|---------|
| **Path Policy** | Block access to `/System`, `/bin`, `/usr`, etc. | Enabled |
| **Write Scope** | Block write actions outside `$HOME` | Enabled |
| **Git Scope** | Block git operations outside `$HOME` | Enabled |
| **Rate Limit** | Max actions per minute per user | 20/min |
| **Approval Gate** | Require yes/no for destructive actions | Enabled |

### 6.2 Custom Policies

```python
# ~/.jarvis/policies.py
from jarvis.policy.engine import Policy, PolicyDecision

class BlockSpecificPaths(Policy):
    name = "block_specific_paths"
    
    def evaluate(self, request) -> PolicyDecision:
        blocked = ["/tmp/sensitive", "/var/cache"]
        if any(request.args.get("path", "").startswith(p) for p in blocked):
            return PolicyDecision(False, "Blocked by custom policy")
        return PolicyDecision(True, "Allowed")

# Automatically loaded from ~/.jarvis/policies.py
```

---

## 7. LLM Backend Registry

### 7.1 Backend Interface

```python
# jarvis/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMResponse:
    content: str
    model: str
    duration_ms: int
    tokens: int | None = None

class LLMBackend(ABC):
    name: str
    
    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> LLMResponse: ...
    
    @abstractmethod
    def is_available(self) -> bool: ...
    
    def configure(self, **kwargs) -> None: ...
```

### 7.2 Implemented Backends

| Backend | Required | Configuration |
|---------|----------|---------------|
| **Ollama** | `ollama` CLI running | `OLLAMA_URL`, model name |
| **OpenAI** | `OPENAI_API_KEY` env | model: `gpt-4o-mini` |
| **Anthropic** | `ANTHROPIC_API_KEY` env | model: `claude-3-haiku` |
| **None** | N/A | Fallback: rule-based only |

### 7.3 Smart Routing

```python
# Use Ollama for local ops, OpenAI for complex reasoning
llm:
  default_backend: "ollama"
  routing:
    - intent: "simple_command"  # backend: "none" (rule-based)
    - intent: "system_query"   # backend: "ollama"  
    - intent: "complex_reasoning" # backend: "openai"
```

---

## 8. Web Dashboard

### 8.1 Features

- **Dashboard**: Real-time status, recent commands, latency metrics
- **Settings**: Configuration editor with validation
- **Logs**: Searchable audit logs (if enabled)
- **Plugins**: Plugin management UI
- **Health**: Backend status checks with fix suggestions

### 8.2 Tech Stack

- **Backend**: Flask or FastAPI (lightweight)
- **Frontend**: Vanilla JS + minimal CSS (no heavy frameworks)
- **Auth**: Optional password protection

### 8.3 API Endpoints

```
GET  /api/status           # System status
GET  /api/commands         # Recent commands
POST /api/execute          # Execute command (voice or text)
GET  /api/config           # Get config
PUT  /api/config           # Update config
GET  /api/health           # Backend health checks
GET  /api/logs             # Audit logs (if enabled)
WS   /ws/events            # Real-time events
```

---

## 9. Plugin System

### 9.1 Plugin Types

| Plugin Type | Description |
|------------|-------------|
| **Action** | Custom commands |
| **STT** | Speech-to-text backend |
| **TTS** | Text-to-speech backend |
| **LLM** | AI backend |
| **System** | Platform backend |

### 9.2 Plugin Discovery

```python
# Auto-loaded from:
~/.jarvis/plugins/
~/.jarvis/plugins/stt/
~/.jarvis/plugins/tts/
~/.jarvis/plugins/llm/
```

Each plugin is a Python module with `register()` function.

---

## 10. Privacy & Security

### 10.1 Default Behavior

| Feature | Default | Opt-in |
|---------|---------|--------|
| Audit logging | OFF | `JARVIS_AUDIT=1` |
| Metrics | OFF | `JARVIS_METRICS=1` |
| Remote LLM calls | OFF | Use local Ollama |
| Web dashboard | OFF | `JARVIS_WEB_PORT=8080` |

### 10.2 Security Features

- **Sandboxed execution**: subprocess with `preexec_fn` limits
- **Path validation**: block system-critical paths
- **Rate limiting**: prevent abuse
- **Approval gates**: explicit consent for destructive actions
- **No shell=True**: all commands use argument lists

---

## 11. CLI Interface

### 11.1 Commands

```bash
# Start voice assistant
jarvis run                    # Start with defaults
jarvis run --hotkey          # Force hotkey mode
jarvis run --wake            # Force wake-word mode

# Web dashboard
jarvis web                   # Start web dashboard
jarvis web --port 9000       # Custom port
jarvis web --password secret # With auth

# Diagnostics
jarvis doctor                # Run health checks
jarvis doctor --verbose      # Detailed output

# Configuration
jarvis config show           # Show current config
jarvis config edit           # Open in editor

# Plugin management
jarvis plugin list           # List plugins
jarvis plugin install <pkg>  # Install plugin
jarvis plugin enable <name>  # Enable plugin

# Version & info
jarvis --version
jarvis info
```

### 11.2 Python API

```python
from jarvis import Jarvis, run

# Programmatic usage
jarvis = Jarvis()
jarvis.run()

# Or CLI
# $ jarvis run
```

---

## 12. Testing Strategy

### 12.1 Test Layers

| Layer | Tests | Tools |
|-------|-------|-------|
| Unit | Action parsing, policy evaluation | pytest |
| Integration | Full command flows | pytest + fixtures |
| Backend | Each STT/TTS/System backend | Mocked/real |
| UI | Web dashboard | Playwright/Selenium |

### 12.2 CI/CD

- **GitHub Actions** on push/PR
- **Test matrix**: Python 3.10, 3.11, 3.12
- **Lint**: ruff, mypy
- **Coverage**: >80% target

---

## 13. Dependencies

### 13.1 Core (Required)

```toml
dependencies = [
    "requests>=2.31.0",
    "pyyaml>=6.0",
]
```

### 13.2 Optional

```toml
[project.optional-dependencies]
audio = [
    "pyaudio>=0.2.14",
    "webrtcvad>=2.0.10",
]
ml = [
    "faster-whisper>=0.10.0",
    "openwakeword>=0.1.0",
]
tts = [
    "pyttsx3>=2.90",
]
web = [
    "flask>=3.0.0",
    "flask-socketio>=5.0.0",
]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]
```

---

## 14. Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Project skeleton created
- [ ] pyproject.toml with dependencies
- [ ] Core routing logic implemented
- [ ] Basic action registry

### Phase 2: Platform Abstraction (Weeks 3-4)
- [ ] STT backends: Apple, Whisper, Google
- [ ] TTS backends: macOS, espeak, pyttsx3
- [ ] System backends: macOS, Linux, Windows
- [ ] All platform code abstracted

### Phase 3: LLM Layer (Weeks 5-6)
- [ ] LLM backend protocol
- [ ] Ollama backend
- [ ] OpenAI backend (optional)
- [ ] Smart routing

### Phase 4: Web Dashboard (Weeks 7-8)
- [ ] Flask/FastAPI app
- [ ] Dashboard UI
- [ ] REST API
- [ ] Real-time events (WebSocket)

### Phase 5: Polish (Weeks 9-10)
- [ ] Plugin system
- [ ] Privacy defaults
- [ ] Documentation
- [ ] First release

---

## 15. Open Questions

1. **GitHub repo URL** for `pyproject.toml`?
2. **Maintainer contact** for package metadata?
3. **Backward compatibility** with existing `jarvis_clean.py` during transition?
4. **Test migration** — preserve and update existing 50+ tests?

---

*End of Specification*