"""Small, embeddable integrations for the existing NOX OneHost."""
from .config import Config
from .core import BridgeError
from .drive import DriveAdapter
from .host import IntegrationBridge, CAPABILITIES
from .memfd import MemfdHandle

__version__ = "0.2.0"
__all__ = ["Config", "BridgeError", "DriveAdapter", "IntegrationBridge", "CAPABILITIES", "MemfdHandle"]
