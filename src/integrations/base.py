"""
Base Integration Adapter — abstract interface for external service integrations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IntegrationAdapter(ABC):
    """Base class for integration adapters."""

    integration_type: str = ""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def execute(self, action: str, params: dict) -> dict:
        """
        Execute an integration action.

        Args:
            action: Action name (e.g., "check_availability", "create_booking")
            params: Action-specific parameters

        Returns:
            Result dict with at least {"success": bool}
        """

