from collections.abc import Callable

from autumn.core.security.registry import register_policy


def _values(target, attribute: str, values: tuple[str, ...]):
    normalized = tuple(str(value).strip() for value in values)

    if not normalized or any(not value for value in normalized):
        raise ValueError('Security requirement values must not be empty')

    current = tuple(getattr(target, attribute, ()))
    setattr(target, attribute, (*current, *normalized))
    return target


def authenticated(target):
    setattr(target, '__autumn_security_authenticated__', True)
    return target


def public(target):
    setattr(target, '__autumn_security_public__', True)
    return target


def roles(*names: str):
    return lambda target: _values(target, '__autumn_security_roles__', names)


def permissions(*names: str):
    return lambda target: _values(target, '__autumn_security_permissions__', names)


def requires(*names: str):
    return lambda target: _values(target, '__autumn_security_policies__', names)


def policy(name: str):
    def decorator(func: Callable):
        register_policy(name, func)
        setattr(func, '__autumn_policy_name__', name)
        return func

    return decorator
