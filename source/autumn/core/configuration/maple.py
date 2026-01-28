from typing import Generic, TypeVar, Annotated, Any

T = TypeVar('T')

class AliasMeta:
    def __init__(self, path: str) -> None:
        self.path = path

class Maple(Generic[T]):
    def __class_getitem__(cls, item: Any):
        path, type = item

        if not isinstance(path, str) or not path:
            raise TypeError('Maple path must be non-empty string')

        return Annotated[type, AliasMeta(path)]