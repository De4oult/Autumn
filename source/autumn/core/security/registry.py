from typing import Callable


POLICIES: dict[str, Callable] = {}


def register_policy(name: str, func: Callable) -> Callable:
    normalized = str(name).strip()

    if not normalized:
        raise ValueError('Policy name must not be empty')

    existing = POLICIES.get(normalized)

    if existing is not None and existing is not func:
        raise ValueError(f'Policy is already registered: {normalized}')

    POLICIES[normalized] = func
    return func


def get_policy(name: str) -> Callable | None:
    return POLICIES.get(name)


def reset_security_registry() -> None:
    POLICIES.clear()
