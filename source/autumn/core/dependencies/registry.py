from __future__ import annotations

from typing import Callable, Any, List, Type

DEPENDENCY_FUNCTIONS: List[Callable[..., Any]] = []
SERVICE_CLASSES: List[Type[Any]] = []