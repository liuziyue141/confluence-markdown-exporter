"""Customer configuration compatibility layer."""

# Re-export CustomerConfig from shared models for backward compatibility
from ..shared.models import CustomerConfig

__all__ = ["CustomerConfig"] 