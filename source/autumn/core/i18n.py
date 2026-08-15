from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from colorama import Fore

from autumn.core.request.request import Request
from autumn.core.resources import Resources, ResourceType


PluralRule = Callable[[int | float], str]


@dataclass(frozen = True)
class Locale:
    code: str


class I18n:
    def __init__(
        self,
        locale: Locale,
        messages: Mapping[str, Any],
        plural_rules: Mapping[str, PluralRule] | None = None
    ) -> None:
        self.locale = locale
        self.messages = messages
        self.plural_rules = plural_rules or {}

    def __resolve(self, key: str) -> Any:
        current: Any = self.messages

        for part in key.split('.'):
            if not isinstance(current, Mapping) or part not in current:
                return None

            current = current[part]

        return current

    def t(self, key: str, **params: Any) -> str:
        current = self.__resolve(key)

        if not isinstance(current, str):
            return key

        return self.__format(current, key, params)

    def plural(
        self,
        key: str,
        count: int | float,
        *,
        rule: str | PluralRule | None = None,
        **params: Any
    ) -> str:
        current = self.__resolve(key)

        if not isinstance(current, Mapping):
            return key

        variant = self.__select_plural_variant(count, rule)
        message = current.get(variant) or current.get('many')

        if not isinstance(message, str):
            return key

        return self.__format(message, key, {'count': count, **params})

    def __select_plural_variant(
        self,
        count: int | float,
        rule: str | PluralRule | None
    ) -> str:
        if callable(rule):
            return str(rule(count))

        if isinstance(rule, str):
            selected_rule = self.plural_rules.get(rule)

            if selected_rule is not None:
                return str(selected_rule(count))

        selected_rule = (
            self.plural_rules.get(self.locale.code)
            or self.plural_rules.get('default')
        )

        if selected_rule is not None:
            return str(selected_rule(count))

        return 'one' if count == 1 else 'many'

    def __format(self, value: str, key: str, params: Mapping[str, Any]) -> str:
        if not params:
            return value

        try:
            return value.format(**params)

        except Exception:
            return value


def warn(message: str) -> None:
    print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + message)


def select_locale(
    request: Request,
    *,
    supported_locales: tuple[str, ...],
    default_locale: str,
    header: str
) -> str:
    requested = request.header(header)

    if requested:
        candidates = []

        for index, chunk in enumerate(requested.split(',')):
            value, *parameters = [part.strip() for part in chunk.split(';')]
            quality = 1.0

            for parameter in parameters:
                if not parameter.startswith('q='):
                    continue

                try:
                    quality = float(parameter[2:])

                except ValueError:
                    quality = 0.0

            candidates.append((value.lower(), quality, index))

        for value, quality, _ in sorted(candidates, key = lambda item: (-item[1], item[2])):
            if quality <= 0:
                continue

            for locale in supported_locales:
                normalized = locale.lower()

                if value == normalized or value.startswith(f'{normalized}-'):
                    return locale

    return default_locale


def load_locale_messages(resources: Resources, locale: str) -> Mapping[str, Any]:
    file = resources.find(locale)

    if file is None:
        warn(f'Localization resource for locale {locale!r} was not found; translations will fall back to keys')
        return {}

    data = resources.read(file, ResourceType.DATA)

    if not isinstance(data, Mapping):
        warn(f'Localization resource for locale {locale!r} must contain an object; translations will fall back to keys')
        return {}

    return data
