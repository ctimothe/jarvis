"""Web dashboard for Jarvis."""

import json
import threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from jarvis.config import Config, get_config
from jarvis.core.router import Router
from jarvis.audit.logger import AuditLogger

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "jarvis-secret-key-change-in-production"
socketio = SocketIO(app, cors_allowed_origins="*")

config: Config = None
router: Router = None
audit_logger: AuditLogger = None
_command_history: list = []
_lock = threading.Lock()


def create_app(cfg: Config | None = None) -> Flask:
    """Create and configure the Flask app."""
    global config, router, audit_logger
    
    config = cfg or get_config()
    router = Router(config)
    audit_logger = AuditLogger(config)
    
    return app


@app.route("/")
def index():
    """Serve the main dashboard."""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Get system status."""
    from jarvis.llm.ollama import OllamaBackend
    
    llm = OllamaBackend(url=config.llm.url, model=config.llm.model)
    llm_available = llm.is_available()
    
    return jsonify({
        "version": "2.0.0",
        "llm_available": llm_available,
        "llm_backend": config.llm.backend,
        "stt_backend": config.stt.backend,
        "tts_backend": config.tts.backend,
        "trigger_mode": config.trigger.mode,
        "audit_enabled": config.privacy.audit_enabled,
        "metrics_enabled": config.privacy.metrics_enabled,
        "platform": config.platform,
    })


@app.route("/api/commands", methods=["GET"])
def api_commands():
    """Get recent commands."""
    with _lock:
        return jsonify(_command_history[-50:])


@app.route("/api/execute", methods=["POST"])
def api_execute():
    """Execute a command via text input."""
    data = request.get_json()
    text = data.get("text", "").strip()
    
    if not text:
        return jsonify({"error": "Empty command"}), 400
    
    try:
        result = router.route(text)
        
        entry = {
            "text": text,
            "response": result,
            "timestamp": __import__("time").time(),
        }
        
        with _lock:
            _command_history.append(entry)
        
        if audit_logger and config.privacy.audit_enabled:
            audit_logger.log("web_command", entry)
        
        socketio.emit("command_result", entry)
        
        return jsonify({"ok": True, "response": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["GET"])
def api_config_get():
    """Get current configuration."""
    return jsonify(config.to_dict())


@app.route("/api/config", methods=["PUT"])
def api_config_set():
    """Update configuration."""
    data = request.get_json()
    
    for key, value in data.items():
        if hasattr(config, key):
            if hasattr(getattr(config, key), "__dict__"):
                sub = getattr(config, key)
                for subkey, subvalue in value.items():
                    if hasattr(sub, subkey):
                        setattr(sub, subkey, subvalue)
    
    config.save()
    return jsonify({"ok": True})


@app.route("/api/health")
def api_health():
    """Run health checks."""
    from jarvis.llm.ollama import OllamaBackend
    
    results = []
    
    llm = OllamaBackend(url=config.llm.url, model=config.llm.model)
    results.append({
        "name": "llm",
        "status": "ok" if llm.is_available() else "unavailable",
    })
    
    results.append({
        "name": "tts",
        "status": "ok" if config.is_macos else "limited",
    })
    
    results.append({
        "name": "audit",
        "status": "enabled" if config.privacy.audit_enabled else "disabled",
    })
    
    return jsonify({"health": results})


@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection."""
    print("Client connected to dashboard")


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    print("Client disconnected from dashboard")


def run_server(host: str = "localhost", port: int = 8080, debug: bool = False):
    """Run the web server."""
    create_app()
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run_server(debug=True)