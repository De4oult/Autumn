from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen = True)
class Principal:
    id: str
    scheme: str
    claims: Mapping[str, Any] = field(default_factory = dict)
    roles: frozenset[str] = field(default_factory = frozenset)
    permissions: frozenset[str] = field(default_factory = frozenset)
    authenticated: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, 'claims', MappingProxyType(dict(self.claims)))
        object.__setattr__(self, 'roles', frozenset(self.roles))
        object.__setattr__(self, 'permissions', frozenset(self.permissions))


class AnonymousPrincipal(Principal):
    def __init__(self) -> None:
        super().__init__(id = '', scheme = '', authenticated = False)
