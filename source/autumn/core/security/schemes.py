from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

import base64
import hashlib
import hmac
import inspect
import json
import time

from autumn.core.request.request import Request
from autumn.core.security.principal import Principal


class AuthenticationScheme(Protocol):
    name: str
    challenge: str

    async def authenticate(self, request: Request) -> Principal | None:
        ...

    def openapi_scheme(self) -> dict[str, Any]:
        ...


PrincipalLoader = Callable[[str], Principal | None | Awaitable[Principal | None]]


class APIKey:
    def __init__(
        self,
        loader: PrincipalLoader,
        *,
        name: str = 'apiKey',
        header: str = 'X-API-Key'
    ) -> None:
        self.loader = loader
        self.name = name
        self.header = header
        self.challenge = 'ApiKey'

    async def authenticate(self, request: Request) -> Principal | None:
        credential = request.header(self.header)

        if not credential:
            return None

        principal = self.loader(credential)

        if inspect.isawaitable(principal):
            principal = await principal

        return principal

    def openapi_scheme(self) -> dict[str, Any]:
        return {'type': 'apiKey', 'in': 'header', 'name': self.header}


class JWTBearer:
    def __init__(
        self,
        secret: str | bytes,
        *,
        issuer: str | None = None,
        audience: str | None = None,
        algorithm: str = 'HS256',
        leeway_seconds: int = 0,
        name: str = 'bearerAuth',
        roles_claim: str = 'roles',
        permissions_claim: str = 'permissions',
        max_token_bytes: int = 8192
    ) -> None:
        if algorithm != 'HS256':
            raise ValueError('JWTBearer currently supports only the explicitly selected HS256 algorithm')

        self.secret = secret.encode() if isinstance(secret, str) else bytes(secret)
        self.issuer = issuer
        self.audience = audience
        self.algorithm = algorithm
        self.leeway_seconds = int(leeway_seconds)
        self.name = name
        self.roles_claim = roles_claim
        self.permissions_claim = permissions_claim
        self.max_token_bytes = int(max_token_bytes)
        self.challenge = 'Bearer'

    @staticmethod
    def _decode_part(value: str) -> dict[str, Any]:
        padding = '=' * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode('ascii'))
        result = json.loads(decoded)

        if not isinstance(result, dict):
            raise ValueError('JWT part must be an object')

        return result

    @staticmethod
    def _string_set(value: Any) -> frozenset[str]:
        if isinstance(value, str):
            return frozenset(item for item in value.split() if item)

        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(str(item) for item in value)

        return frozenset()

    async def authenticate(self, request: Request) -> Principal | None:
        authorization = request.header('authorization')

        if not authorization:
            return None

        kind, separator, token = authorization.partition(' ')

        if kind.lower() != 'bearer' or not separator or not token or len(token.encode()) > self.max_token_bytes:
            return None

        try:
            header_part, payload_part, signature_part = token.split('.')
            header = self._decode_part(header_part)
            claims = self._decode_part(payload_part)

            if header.get('alg') != self.algorithm:
                return None

            signed = f'{header_part}.{payload_part}'.encode('ascii')
            padding = '=' * (-len(signature_part) % 4)
            signature = base64.urlsafe_b64decode((signature_part + padding).encode('ascii'))
            expected = hmac.new(self.secret, signed, hashlib.sha256).digest()

            if not hmac.compare_digest(signature, expected):
                return None

            now = time.time()
            leeway = self.leeway_seconds

            if 'exp' not in claims or float(claims['exp']) < now - leeway:
                return None

            if 'nbf' in claims and float(claims['nbf']) > now + leeway:
                return None

            if self.issuer is not None and claims.get('iss') != self.issuer:
                return None

            audience = claims.get('aud')
            audiences = {audience} if isinstance(audience, str) else set(audience or ())

            if self.audience is not None and self.audience not in audiences:
                return None

            subject = claims.get('sub')

            if not isinstance(subject, str) or not subject:
                return None

            return Principal(
                id = subject,
                scheme = self.name,
                claims = claims,
                roles = self._string_set(claims.get(self.roles_claim)),
                permissions = self._string_set(claims.get(self.permissions_claim))
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def openapi_scheme(self) -> dict[str, Any]:
        return {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}
