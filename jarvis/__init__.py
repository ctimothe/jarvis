"""Jarvis Open - Privacy-first, extensible voice assistant."""

__version__ = "2.0.0"
__author__ = "Your Name"

from jarvis.config import Config
from jarvis.core.router import Router

def run() -> None:
    """Run the Jarvis assistant."""
    config = Config.load()
    router = Router(config)
    router.run()

class Jarvis:
    """Main Jarvis assistant class."""
    
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.router = Router(self.config)
    
    def run(self) -> None:
        """Start the Jarvis assistant."""
        self.router.run()
    
    def stop(self) -> None:
        """Stop the Jarvis assistant."""
        self.router.stop()