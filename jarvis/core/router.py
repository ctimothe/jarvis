"""Router - routes input to appropriate handler."""

from jarvis.config import Config
from jarvis.types import ActionRequest, MissionPlan
from jarvis.core.classifier import Classifier, Intent
from jarvis.actions.base import get_action_registry
from jarvis.policy.engine import PolicyEngine
from jarvis.audit.logger import AuditLogger


class Router:
    """Main router that coordinates all components."""

    def __init__(self, config: Config):
        self.config = config
        self.classifier = Classifier(config)
        self.policy_engine = PolicyEngine(config)
        self.action_registry = get_action_registry()
        self.audit_logger = AuditLogger(config)

    def route(self, text: str) -> str:
        """Route input text to appropriate handler."""
        if not text.strip():
            return "I didn't catch that."

        # Check for mission control commands
        # (execute mission, cancel mission, etc.)

        # Try deterministic shell path first
        request = self._build_action_request(text)
        if request:
            # Check policy
            decision = self.policy_engine.evaluate(request)
            if not decision.allowed:
                return f"Blocked by policy: {decision.reason}"

            # Execute action
            result = self.action_registry.execute(request)
            return self._format_result(result)

        # Fall back to classifier
        intent = self.classifier.classify(text)
        return self._handle_intent(intent, text)

    def _build_action_request(self, text: str) -> ActionRequest | None:
        """Build action request from text using regex patterns."""
        # This will delegate to action registry's parser
        return self.action_registry.parse(text)

    def _handle_intent(self, intent: Intent, text: str) -> str:
        """Handle classified intent."""
        if intent == Intent.STOP:
            return ""  # Stop speaking

        if intent == Intent.QUESTION:
            # Use LLM to answer
            from jarvis.llm.registry import get_llm_registry
            llm = get_llm_registry().get_backend()
            if llm and llm.is_available():
                return llm.complete(text)
            return "AI is unavailable. Ask a direct command like battery, volume, or open app."

        if intent == Intent.OPEN_APP:
            # Delegate to actions
            return "Opening app..."  # TODO: implement

        if intent == Intent.MUSIC:
            return "Controlling music..."  # TODO: implement

        if intent == Intent.SYSTEM:
            return "System action..."  # TODO: implement

        if intent == Intent.WORK_MODE:
            return "Activating work mode..."  # TODO: implement

        return "I didn't understand that. Try a direct command."

    def _format_result(self, result) -> str:
        """Format action result for TTS."""
        if not result.ok and not result.stdout:
            return f"That failed: {(result.stderr or 'unknown error')[:150]}"

        if result.ok and not result.stdout:
            return "Done."

        if result.stdout and len(result.stdout) < 120 and "\n" not in result.stdout:
            return result.stdout

        # Too long - summarize
        snippet = result.stdout[:600]
        from jarvis.llm.registry import get_llm_registry
        llm = get_llm_registry().get_backend()
        if llm and llm.is_available():
            summary = llm.complete(
                f"Summarize this output in one sentence: {snippet}",
                system="You are a helpful assistant."
            )
            return summary or f"Done. {len(result.stdout.splitlines())} lines of output."

        return f"Done. {len(result.stdout.splitlines())} lines of output."

    def run(self) -> None:
        """Start the router (main loop)."""
        # TODO: Initialize STT, TTS, trigger handlers
        pass

    def stop(self) -> None:
        """Stop the router."""
        # TODO: Cleanup
        pass