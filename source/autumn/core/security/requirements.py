from dataclasses import dataclass


@dataclass(frozen = True)
class SecurityRequirements:
    public: bool = False
    authenticated: bool = False
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    policies: tuple[str, ...] = ()

    @property
    def required(self) -> bool:
        return self.authenticated or bool(self.roles or self.permissions or self.policies)


def requirements_for(controller: type | None, handler) -> SecurityRequirements:
    method_public = bool(getattr(handler, '__autumn_security_public__', False))

    if method_public:
        return SecurityRequirements(public = True)

    objects = tuple(item for item in (controller, handler) if item is not None)

    roles = frozenset(
        role
        for item in objects
        for role in getattr(item, '__autumn_security_roles__', ())
    )
    permissions = frozenset(
        permission
        for item in objects
        for permission in getattr(item, '__autumn_security_permissions__', ())
    )
    policies = tuple(dict.fromkeys(
        policy
        for item in objects
        for policy in getattr(item, '__autumn_security_policies__', ())
    ))
    authenticated = any(
        getattr(item, '__autumn_security_authenticated__', False)
        for item in objects
    ) or bool(roles or permissions or policies)

    return SecurityRequirements(
        authenticated = authenticated,
        roles = roles,
        permissions = permissions,
        policies = policies
    )
