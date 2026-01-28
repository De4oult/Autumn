from autumn.core.configuration.errors import AutumnConfigAliasError

from dataclasses import dataclass

@dataclass(frozen = True, slots = True)
class Alias:
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise AutumnConfigAliasError('Alias path must be non-empty string')