"""Small compatibility aliases for the oldest supported Python release."""

from __future__ import annotations

from datetime import timezone
from enum import Enum

UTC = timezone.utc

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - exercised on Python 3.10

    class StrEnum(str, Enum):
        """Python 3.10 equivalent of :class:`enum.StrEnum`."""

        def __str__(self) -> str:
            return str(self.value)
