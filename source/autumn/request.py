from uuid import UUID

from .core.request.request import Request
from .core.request.query import QueryBuilder

class __QueryNamespace:
    string = staticmethod(QueryBuilder(str))
    int    = staticmethod(QueryBuilder(int))
    float  = staticmethod(QueryBuilder(float))
    uuid   = staticmethod(QueryBuilder(UUID))

query = __QueryNamespace()

__all__ = (
    'Request',
    
    query
)