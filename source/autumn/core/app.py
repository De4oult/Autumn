from autumn.core.websocket.websocket import WebSocket, WebSocketDisconnect
from autumn.core.configuration.builtin import ApplicationConfiguration, CORSConfiguration, LocalizationConfiguration, WebUIConfiguration
from autumn.core.configuration.configuration import Configuration, get_registered_configs
from autumn.core.dependencies import registry as dependency_registry
from autumn.core.dependencies.container import Container, ExecutionContext, is_union_dependency, union_dependency_args
from autumn.core.exception.exception import DependencyInjectionError
from autumn.core.introspection import get_declared_body_parameter
from autumn.core.serialization import value_supports_json_response
from autumn.core.middleware.manager import MiddlewareManager, MiddlewarePlan
from autumn.core.environment import Environment
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import JSONResponse, Response
from autumn.core.dependencies.scope import Scope
from autumn.core.request.request import Request
from autumn.core.routing.router import Router
from autumn.core.security.configuration import SecurityConfiguration
from autumn.core.security.principal import AnonymousPrincipal, Principal
from autumn.core.security.registry import get_policy
from autumn.core.security.requirements import SecurityRequirements, requirements_for
from autumn.core.i18n import I18n, Locale, load_locale_messages, select_locale

from typing import Any, Callable, Optional, Sequence, get_type_hints
from pathlib import Path
from uuid import uuid4
from colorama import Fore
from dataclasses import dataclass

import importlib
import importlib.util
import pkgutil
import asyncio
import inspect
import types
import time
import sys


@dataclass(frozen = True)
class HTTPExecutionPlan:
    handler_callable: Callable
    is_controller: bool
    query_metadata: tuple[dict, ...]
    middleware: MiddlewarePlan
    security: SecurityRequirements

class Autumn:
    def __init__(
        self,
        *,
        environment: Environment = Environment.DEVELOPMENT,
        discover: Optional[str | Sequence[str]] = None,
        root_path: Optional[str | Path] = None
    ):
        self.environment: Environment = environment
        caller_file = inspect.stack()[1].filename
        self.__entrypoint_path: Optional[Path] = Path(caller_file).resolve() if caller_file else None
        self.__root_path: Optional[Path] = Path(root_path).resolve() if root_path is not None else (
            self.__entrypoint_path.parent if self.__entrypoint_path is not None else None
        )
        if isinstance(discover, bool):
            raise TypeError(
                'discover must contain explicit module names, '
                "for example discover=('controllers.users', 'services.users')"
            )

        if not discover:
            self.__discovery_modules: tuple[str, ...] = ()
        elif isinstance(discover, str):
            self.__discovery_modules = (discover,)
        else:
            self.__discovery_modules = tuple(str(module) for module in discover)

        self.__discovery_completed: bool = False
        self.__discovery_package: str = f'_autumn_discovered_{id(self)}'

        self.router = Router()
        
        self.startup_hooks: list[Callable] = []
        self.shutdown_hooks: list[Callable] = []
        
        self.middleware = MiddlewareManager()
        self.container = Container()
        self.__application_configuration: Optional[ApplicationConfiguration] = None
        self.__cors_configuration: Optional[CORSConfiguration] = None
        self.__localization_configuration: Optional[LocalizationConfiguration] = None
        self.__webui_configuration = None
        self.__security_configuration: Optional[SecurityConfiguration] = None
        self.__http_handler_cache: dict[tuple[type, str], Callable] = {}
        self.__websocket_handler_cache: dict[tuple[type, str], Callable] = {}
        self.__controllers: list[type] = []
        self.__route_functions: list[Callable] = []
        self.__dependency_functions: list[Callable] = []
        self.__configuration_classes: list[type[Configuration]] = []
        self.__service_classes: list[type] = []
        self.__middleware_entries: list[tuple[str, Callable, Optional[str | Sequence[str]], Optional[str | Sequence[str]]]] = []
        self.__disabled_provider_reasons: dict[Any, str] = {}
        self.__disabled_definitions: set[Any] = set()
        self.__provider_definitions: dict[Any, Any] = {}
        self.__environment_dependency_warnings: set[str] = set()

        self.__providers_synced: bool = False

        self.__resolve_base_routes()

    @property
    def name(self) -> str:
        return self.__get_application_metadata('name')

    @property
    def version(self) -> str:
        return self.__get_application_metadata('version')

    @property
    def description(self) -> Optional[str]:
        return self.__get_application_metadata('description')

    @property
    def application_configuration(self) -> Optional[ApplicationConfiguration]:
        if not self.__providers_synced or self.__application_configuration is None:
            self.__sync_providers()

        return self.__application_configuration

    @property
    def webui_configuration(self):
        if not self.__providers_synced or self.__webui_configuration is None:
            self.__sync_providers()

        return self.__webui_configuration

    def __get_application_metadata(self, name: str):
        configuration = self.application_configuration

        if configuration is None:
            return getattr(ApplicationConfiguration, name, None)

        return getattr(configuration, name, None)

    @staticmethod
    def __append_unique(collection: list, item) -> bool:
        if item in collection:
            return False

        collection.append(item)
        return True

    @staticmethod
    def __normalize_environment_values(values) -> tuple[Environment, ...]:
        if isinstance(values, (str, Environment)):
            values = (values, )

        return tuple(
            item if isinstance(item, Environment) else Environment(str(item))
            for item in values
        )

    def __only_environments_for(self, definition) -> Optional[tuple[Environment, ...]]:
        values = getattr(definition, '__autumn_only_environments__', None)

        if values is None:
            return None

        return self.__normalize_environment_values(values)

    def __definition_is_allowed(self, definition) -> bool:
        allowed_on = self.__only_environments_for(definition)

        return allowed_on is None or self.environment in allowed_on

    def __definition_is_allowed_for(self, definition, environment: Environment) -> bool:
        allowed_on = self.__only_environments_for(definition)

        return allowed_on is None or environment in allowed_on

    def __environment_label(self, environment: Environment) -> str:
        return environment.value if isinstance(environment, Environment) else str(environment)

    def __only_error_message(self, definition, provider_key: Any) -> str:
        allowed_on = self.__only_environments_for(definition) or ()
        allowed = ', '.join(self.__environment_label(item) for item in allowed_on) or 'none'
        name = getattr(definition, '__qualname__', None) or getattr(definition, '__name__', None) or repr(definition)
        key_name = getattr(provider_key, '__qualname__', None) or getattr(provider_key, '__name__', None) or repr(provider_key)

        return (
            f'{key_name} is only allowed on {allowed}, '
            f'but current environment is {self.environment.value} ({name})'
        )

    def __provider_key_for_definition(self, definition) -> Optional[Any]:
        if inspect.isclass(definition):
            return definition

        provider_meta = getattr(definition, '__autumn_provider__', None)

        if provider_meta and provider_meta[0] == 'func':
            try:
                return get_type_hints(definition).get('return')

            except Exception:
                return None

        return definition if callable(definition) else None

    def __warn(self, message: str) -> None:
        print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + message)

    def __record_disabled_definition(self, definition) -> None:
        self.__disabled_definitions.add(definition)
        key = self.__provider_key_for_definition(definition)

        if key is not None:
            self.__disabled_provider_reasons[key] = self.__only_error_message(definition, key)

    @staticmethod
    def __normalize_route_path(path: str) -> str:
        value = str(path or '/').strip()

        if not value:
            return '/'

        if not value.startswith('/'):
            value = '/' + value

        return value

    @classmethod
    def __join_paths(cls, prefix: str, path: str) -> str:
        normalized_prefix = '' if prefix == '/' else cls.__normalize_route_path(prefix).rstrip('/')
        normalized_path = cls.__normalize_route_path(path)

        if not normalized_prefix:
            return normalized_path

        if normalized_path == '/':
            return normalized_prefix or '/'

        return normalized_prefix + normalized_path

    def __register_routes_for_controller(self, controller_class: type) -> None:
        prefix = getattr(controller_class, '__autumn_prefix__', '')

        for name, attribute in controller_class.__dict__.items():
            routes = getattr(attribute, '__routes__', None)

            if not routes:
                continue

            for route in routes:
                full_path = self.__join_paths(prefix, route.get('path', '/'))
                method = route.get('method', 'GET')

                if method == 'WS':
                    self.router.add_websocket_route(full_path, (controller_class, name))
                else:
                    self.router.add_route(method, full_path, (controller_class, name))

    def __register_routes_for_function(self, func: Callable) -> None:
        routes = getattr(func, '__routes__', None) or []

        for route in routes:
            path = self.__normalize_route_path(route.get('path', '/'))
            method = route.get('method', 'GET')

            if method == 'WS':
                self.router.add_websocket_route(path, func)
            else:
                self.router.add_route(method, path, func)

    def __ensure_discovery_package(self, module_name: str, filepath: Path) -> None:
        parts = module_name.split('.')

        for index in range(1, len(parts)):
            package_name = '.'.join(parts[:index])

            if package_name in sys.modules:
                continue

            package = types.ModuleType(package_name)

            if index == 1 or self.__root_path is None:
                package_path = self.__root_path or filepath.parent

            else:
                package_path = self.__root_path.joinpath(*parts[1:index])

            package.__path__ = [str(package_path)]
            sys.modules[package_name] = package

    def __load_discovery_file(
        self,
        requested_module: str,
        filepath: Path,
        *,
        is_package: bool = False
    ) -> None:
        module_name = f'{self.__discovery_package}.{requested_module}'

        if module_name in sys.modules:
            return

        self.__ensure_discovery_package(module_name, filepath)
        spec = importlib.util.spec_from_file_location(
            module_name,
            filepath,
            submodule_search_locations = [str(filepath.parent)] if is_package else None
        )

        if spec is None or spec.loader is None:
            raise ImportError(f'Unable to load discovery module: {requested_module!r}')

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

    def __discover_local_package(self, requested_module: str, package_path: Path) -> None:
        package_path = package_path.resolve()
        files = list(package_path.rglob('*.py'))

        def module_details(filepath: Path) -> tuple[str, bool]:
            resolved_filepath = filepath.resolve()

            if not resolved_filepath.is_relative_to(package_path):
                raise PermissionError(
                    f'Discovery module escapes the requested package: {filepath}'
                )

            relative = filepath.relative_to(package_path)
            is_package = relative.name == '__init__.py'
            relative_parts = relative.parent.parts if is_package else relative.with_suffix('').parts
            module_parts = (*requested_module.split('.'), *relative_parts)

            if any(not part.isidentifier() for part in module_parts):
                raise ValueError(f'Invalid Python module in discovery package: {filepath}')

            return '.'.join(module_parts), is_package

        discovered = [(*module_details(filepath), filepath) for filepath in files]
        discovered.sort(key = lambda item: (item[0].count('.'), not item[1], item[0]))

        for module_name, is_package, filepath in discovered:
            self.__load_discovery_file(
                module_name,
                filepath.resolve(),
                is_package = is_package
            )

    def __discover_modules(self) -> None:
        if self.__discovery_completed:
            return

        self.__discovery_completed = True

        if not self.__discovery_modules:
            return

        for requested_module in self.__discovery_modules:
            requested_module = requested_module.strip().strip('.')

            if not requested_module or any(
                part in ('', '.', '..') for part in requested_module.split('.')
            ):
                raise ValueError(f'Invalid discovery module: {requested_module!r}')

            filepath = None
            local_package_path = None

            if self.__root_path is not None:
                module_path = self.__root_path.joinpath(*requested_module.split('.'))
                file_candidate = module_path.with_suffix('.py')
                package_candidate = module_path / '__init__.py'

                if file_candidate.is_file():
                    filepath = file_candidate.resolve()
                elif package_candidate.is_file():
                    local_package_path = module_path.resolve()

            if local_package_path is not None:
                self.__discover_local_package(requested_module, local_package_path)
                continue

            if filepath is not None:
                self.__load_discovery_file(requested_module, filepath)
                continue

            module = importlib.import_module(requested_module)

            if hasattr(module, '__path__'):
                children = sorted(
                    name
                    for _, name, _ in pkgutil.walk_packages(
                        module.__path__,
                        prefix = f'{requested_module}.'
                    )
                )

                for child in children:
                    importlib.import_module(child)

    def __sync_registered_definitions(self) -> None:
        self.__discover_modules()

        (
            controller_classes,
            route_functions,
            dependency_functions,
            service_classes,
            configuration_classes,
            startup_hooks,
            shutdown_hooks,
            middleware_entries
        ) = dependency_registry.registered_definitions()

        for definition in (*dependency_functions, *service_classes):
            key = self.__provider_key_for_definition(definition)

            if key is not None:
                self.__provider_definitions[key] = definition

        for definition in (
            *configuration_classes,
            *controller_classes,
            *route_functions,
            *dependency_functions,
            *service_classes
        ):
            self.__include(definition)

        for hook in startup_hooks:
            if not self.__definition_is_allowed(hook):
                self.__record_disabled_definition(hook)
                continue

            self.__append_unique(self.startup_hooks, hook)

        for hook in shutdown_hooks:
            if not self.__definition_is_allowed(hook):
                self.__record_disabled_definition(hook)
                continue

            self.__append_unique(self.shutdown_hooks, hook)

        for entry in middleware_entries:
            _, func, _, _ = entry

            if not self.__definition_is_allowed(func):
                self.__record_disabled_definition(func)
                continue

            if not self.__append_unique(self.__middleware_entries, entry):
                continue

            kind, func, path, method = entry

            if kind == 'before':
                self.middleware.before(func, path = path, method = method)

            elif kind == 'after':
                self.middleware.after(func, path = path, method = method)

    def __include(self, *definitions) -> None:
        for definition in definitions:
            if definition is None:
                continue

            if isinstance(definition, (list, tuple, set, frozenset)):
                self.__include(*definition)
                continue

            if not self.__definition_is_allowed(definition):
                self.__record_disabled_definition(definition)
                continue

            if inspect.isclass(definition):
                if issubclass(definition, Configuration):
                    if self.__append_unique(self.__configuration_classes, definition):
                        self.__providers_synced = False

                    continue

                if getattr(definition, '__autumn_controller__', False):
                    if self.__append_unique(self.__controllers, definition):
                        self.__register_routes_for_controller(definition)

                    continue

                provider_meta = getattr(definition, '__autumn_provider__', None)

                if provider_meta and provider_meta[0] == 'class':
                    self.__append_unique(self.__service_classes, definition)

                    continue

            if callable(definition):
                routes = getattr(definition, '__routes__', None)

                if routes:
                    if self.__append_unique(self.__route_functions, definition):
                        self.__register_routes_for_function(definition)

                    continue

                provider_meta = getattr(definition, '__autumn_provider__', None)

                if provider_meta and provider_meta[0] == 'func':
                    if self.__append_unique(self.__dependency_functions, definition):
                        self.__providers_synced = False
                        
                    continue

    def get_registered_configs(self) -> list[type[Configuration]]:
        self.__sync_registered_definitions()
        return get_registered_configs(self.__configuration_classes)

    def get_registered_dependency_functions(self) -> list[Callable]:
        self.__sync_registered_definitions()
        return list(self.__dependency_functions)

    def get_registered_controller_classes(self) -> list[type]:
        self.__sync_registered_definitions()
        return list(self.__controllers)

    def get_registered_route_functions(self) -> list[Callable]:
        self.__sync_registered_definitions()
        return list(self.__route_functions)

    def get_registered_service_classes(self) -> list[type]:
        self.__sync_registered_definitions()
        return list(self.__service_classes)

    def __resolve_base_routes(self) -> None:
        from autumn.core.routing.base import favicon_route

        self.__enable_documentation()
        self.router.add_route('GET', '/favicon.ico', favicon_route)

    def is_webui_allowed(self) -> bool:
        configuration = self.webui_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_on = configuration.allowed_on

        if isinstance(allowed_on, (str, Environment)):
            allowed_on = (allowed_on, )

        return self.environment in {
            item if isinstance(item, Environment) else Environment(str(item))
            for item in allowed_on
        }

    def __enable_documentation(self) -> None:
        from autumn.core.routing.base import (
            dependencies_json_route,
            openapi_json_route, 
            autumn_web_route
        )

        self.router.add_route('GET', '/documentation/dependencies.json', dependencies_json_route(self))
        self.router.add_route('GET', '/documentation/openapi.json', openapi_json_route(self))

        self.router.add_route('GET', '/autumn', autumn_web_route(self))
        
    def __sync_providers(self):
        if self.__providers_synced:
            return

        self.__sync_registered_definitions()

        self.__application_configuration = None
        self.__cors_configuration = None
        self.__localization_configuration = None
        self.__webui_configuration = None
        leaf_provider_keys: set[Any] = set()

        for func in self.__dependency_functions:
            try:
                provider_key = get_type_hints(func).get('return')

            except Exception:
                provider_key = None

            if provider_key is not None:
                leaf_provider_keys.add(provider_key)

        allowed_provider_keys = {
            Request,
            Locale,
            I18n,
            Principal,
            WebSocket,
            *self.__controllers,
            *self.__service_classes,
            *self.__configuration_classes,
            *leaf_provider_keys
        }

        self.container.configure_environment(
            allowed_provider_keys = allowed_provider_keys,
            disabled_provider_reasons = dict(self.__disabled_provider_reasons)
        )

        for func in self.__dependency_functions:
            self.container.register_dependency_function(func)

        for configuration_class in self.get_registered_configs():
            configuration = configuration_class.build()

            self.container.register_value(
                configuration_class, 
                configuration, 
                scope = Scope.APP
            )

            for base_class in configuration_class.__mro__[1:]:
                if getattr(base_class, '__autumn_builtin_config__', False):
                    self.container.register_value(
                        base_class,
                        configuration,
                        scope = Scope.APP
                    )

            if issubclass(configuration_class, ApplicationConfiguration):
                self.__application_configuration = configuration

            if issubclass(configuration_class, CORSConfiguration):
                self.__cors_configuration = configuration

            if issubclass(configuration_class, LocalizationConfiguration):
                self.__localization_configuration = configuration

            if issubclass(configuration_class, WebUIConfiguration):
                self.__webui_configuration = configuration

            if issubclass(configuration_class, SecurityConfiguration):
                self.__security_configuration = configuration

        self.__validate_environment_dependency_graph(leaf_provider_keys)

        self.__providers_synced = True
        self.__compile_http_execution_plans()

    def __compile_http_execution_plans(self) -> None:
        for route in self.router.get_routes():
            if route.method == 'WS':
                continue

            handler = route.handler
            is_controller = (
                isinstance(handler, tuple)
                and len(handler) == 2
                and isinstance(handler[1], str)
            )
            handler_callable = (
                self.__get_http_handler_callable(handler)
                if is_controller
                else handler
            )
            security_handler = (
                getattr(handler[0], handler[1])
                if is_controller
                else handler_callable
            )
            security = requirements_for(
                handler[0] if is_controller else None,
                security_handler
            )

            if (
                not security.public
                and not security.required
                and self.__security_configuration is not None
                and self.__security_configuration.fallback_authenticated
            ):
                security = SecurityRequirements(authenticated = True)

            for policy_name in security.policies:
                if get_policy(policy_name) is None:
                    raise RuntimeError(f'Unknown security policy: {policy_name}')

            route.execution_plan = HTTPExecutionPlan(
                handler_callable = handler_callable,
                is_controller = is_controller,
                query_metadata = tuple(
                    getattr(handler_callable, '__query_parameters__', ())
                ),
                middleware = self.middleware.compile(route.path_template, route.method),
                security = security
            )

    def __safe_type_hints(self, callable: Callable[..., Any]) -> dict[str, Any]:
        try:
            return get_type_hints(callable)

        except Exception:
            return {}

    def __dependency_key_available(self, key: Any, provider_keys: set[Any]) -> bool:
        if is_union_dependency(key):
            return any(
                self.__dependency_key_available(candidate, provider_keys)
                for candidate in union_dependency_args(key)
            )

        if key in (Request, Locale, I18n, Principal, WebSocket):
            return True

        if key in self.__disabled_provider_reasons:
            return False

        return key in provider_keys

    def __callable_dependency_keys(
        self,
        callable: Callable[..., Any],
        *,
        skip_self: bool = False,
        provider_keys: set[Any],
        provided_names: set[str] | None = None,
        can_resolve_dependency: Callable[[Any], bool] | None = None
    ) -> list[Any]:
        provided_names = provided_names or set()
        can_resolve_dependency = can_resolve_dependency or (
            lambda key: self.__dependency_key_available(key, provider_keys)
        )

        try:
            signature = inspect.signature(callable)

        except Exception:
            return []

        hints = self.__safe_type_hints(callable)
        body_parameter = None

        try:
            body_parameter = get_declared_body_parameter(
                callable,
                provided_kwargs = {name: object() for name in provided_names},
                skip_self = skip_self,
                can_resolve_dependency = can_resolve_dependency,
                signature = signature,
                hints = hints
            )

        except RuntimeError:
            body_parameter = None

        dependencies: list[Any] = []

        for name, parameter in signature.parameters.items():
            if skip_self and name == 'self':
                continue

            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if name in provided_names:
                continue

            if body_parameter is not None and name == body_parameter.name:
                continue

            if name in hints:
                dependencies.append(hints[name])

        return dependencies

    def __provider_leaf_map(self) -> dict[Any, Callable[..., Any]]:
        leaf_map: dict[Any, Callable[..., Any]] = {}

        for func in self.__dependency_functions:
            key = self.__provider_key_for_definition(func)

            if key is not None:
                leaf_map[key] = func

        return leaf_map

    def __dependency_consumer_name(self, consumer: Any) -> str:
        return getattr(consumer, '__qualname__', None) or getattr(consumer, '__name__', None) or repr(consumer)

    def __dependency_key_name(self, key: Any) -> str:
        return getattr(key, '__qualname__', None) or getattr(key, '__name__', None) or repr(key)

    def __dependency_environment_set(
        self,
        key: Any,
        leaf_map: dict[Any, Callable[..., Any]]
    ) -> set[Environment]:
        definition = self.__provider_definitions.get(key, leaf_map.get(key, key))
        allowed_on = self.__only_environments_for(definition)

        if allowed_on is None:
            return set(Environment)

        return set(allowed_on)

    def __validate_union_dependency_key(
        self,
        key: Any,
        *,
        consumer: Any,
        provider_keys: set[Any],
        leaf_map: dict[Any, Callable[..., Any]],
        stack: tuple[Any, ...]
    ) -> None:
        candidates = union_dependency_args(key)

        if len(candidates) < 2:
            raise DependencyInjectionError(
                f'{self.__dependency_consumer_name(consumer)} requires an invalid union dependency: {key!r}'
            )

        environment_sets = {
            candidate: self.__dependency_environment_set(candidate, leaf_map)
            for candidate in candidates
        }

        for index, left in enumerate(candidates):
            for right in candidates[index + 1:]:
                overlap = environment_sets[left] & environment_sets[right]

                if overlap:
                    environments = ', '.join(
                        self.__environment_label(environment)
                        for environment in sorted(overlap, key = lambda item: item.value)
                    )
                    raise DependencyInjectionError(
                        f'{self.__dependency_consumer_name(consumer)} has overlapping @only environments '
                        f'for union dependency {self.__dependency_key_name(left)} | {self.__dependency_key_name(right)}: '
                        f'{environments}'
                    )

        active_candidates = tuple(
            candidate
            for candidate in candidates
            if self.environment in environment_sets[candidate]
        )

        if not active_candidates:
            candidate_names = ' | '.join(self.__dependency_key_name(candidate) for candidate in candidates)
            raise DependencyInjectionError(
                f'{self.__dependency_consumer_name(consumer)} requires {candidate_names}, '
                f'but no union dependency is active for {self.environment.value}'
            )

        for candidate in active_candidates:
            self.__validate_dependency_key(
                candidate,
                consumer = consumer,
                provider_keys = provider_keys,
                leaf_map = leaf_map,
                stack = stack
            )

    def __validate_dependency_key(
        self,
        key: Any,
        *,
        consumer: Any,
        provider_keys: set[Any],
        leaf_map: dict[Any, Callable[..., Any]],
        stack: tuple[Any, ...]
    ) -> None:
        if is_union_dependency(key):
            self.__validate_union_dependency_key(
                key,
                consumer = consumer,
                provider_keys = provider_keys,
                leaf_map = leaf_map,
                stack = stack
            )
            return

        disabled_reason = self.__disabled_provider_reasons.get(key)

        if disabled_reason is not None:
            raise DependencyInjectionError(
                f'{self.__dependency_consumer_name(consumer)} requires {disabled_reason}'
            )

        if key in (Request, Locale, I18n, Principal, WebSocket):
            return

        if key not in provider_keys:
            raise DependencyInjectionError(
                f'{self.__dependency_consumer_name(consumer)} requires {self.__dependency_key_name(key)}, but no provider is registered'
            )

        self.__validate_provider_key(
            key,
            provider_keys = provider_keys,
            leaf_map = leaf_map,
            stack = stack
        )

    def __validate_provider_key(
        self,
        key: Any,
        *,
        provider_keys: set[Any],
        leaf_map: dict[Any, Callable[..., Any]],
        stack: tuple[Any, ...] = ()
    ) -> None:
        if key in (Request, Locale, I18n, Principal, WebSocket) or key in self.__configuration_classes:
            return

        if key in stack:
            return

        if key in self.__service_classes or key in self.__controllers:
            callable = key.__init__
            dependencies = self.__callable_dependency_keys(
                callable,
                skip_self = True,
                provider_keys = provider_keys
            )

        elif key in leaf_map:
            callable = leaf_map[key]
            dependencies = self.__callable_dependency_keys(
                callable,
                provider_keys = provider_keys
            )

        else:
            return

        for dependency in dependencies:
            self.__validate_dependency_key(
                dependency,
                consumer = callable,
                provider_keys = provider_keys,
                leaf_map = leaf_map,
                stack = (*stack, key)
            )

    def __validate_route_handler_dependencies(
        self,
        route,
        *,
        provider_keys: set[Any],
        leaf_map: dict[Any, Callable[..., Any]]
    ) -> None:
        provided_names = {'request', 'websocket', *route.parameters}

        if isinstance(route.handler, tuple) and len(route.handler) == 2 and isinstance(route.handler[1], str):
            controller_class, method_name = route.handler
            method = getattr(controller_class, method_name)

            self.__validate_provider_key(
                controller_class,
                provider_keys = provider_keys,
                leaf_map = leaf_map
            )

            callable = method
            skip_self = True

        else:
            callable = route.handler
            skip_self = False

        for query in getattr(callable, '__query_parameters__', []) or []:
            name = query.get('name')

            if name:
                provided_names.add(name)

        dependencies = self.__callable_dependency_keys(
            callable,
            skip_self = skip_self,
            provided_names = provided_names,
            provider_keys = provider_keys
        )

        for dependency in dependencies:
            self.__validate_dependency_key(
                dependency,
                consumer = callable,
                provider_keys = provider_keys,
                leaf_map = leaf_map,
                stack = ()
            )

    def __validate_environment_dependency_graph(self, leaf_provider_keys: set[Any]) -> None:
        provider_keys = {
            Request,
            WebSocket,
            *self.__controllers,
            *self.__service_classes,
            *self.__configuration_classes,
            *leaf_provider_keys
        }
        leaf_map = self.__provider_leaf_map()

        for service_class in self.__service_classes:
            self.__validate_provider_key(
                service_class,
                provider_keys = provider_keys,
                leaf_map = leaf_map
            )

        for leaf_key in leaf_provider_keys:
            self.__validate_provider_key(
                leaf_key,
                provider_keys = provider_keys,
                leaf_map = leaf_map
            )

        for route in self.router.get_routes():
            self.__validate_route_handler_dependencies(
                route,
                provider_keys = provider_keys,
                leaf_map = leaf_map
            )

        self.__warn_about_inactive_environment_dependency_graphs()

    def __dependency_key_available_for_environment(self, key: Any, provider_keys: set[Any]) -> bool:
        if is_union_dependency(key):
            return any(
                self.__dependency_key_available_for_environment(candidate, provider_keys)
                for candidate in union_dependency_args(key)
            )

        if key in (Request, Locale, I18n, Principal, WebSocket):
            return True

        return key in provider_keys

    def __provider_keys_for_environment(
        self,
        environment: Environment,
        dependency_functions: Sequence[Callable[..., Any]],
        service_classes: Sequence[type],
        configuration_classes: Sequence[type[Configuration]]
    ) -> tuple[set[Any], dict[Any, Callable[..., Any]]]:
        leaf_map: dict[Any, Callable[..., Any]] = {}

        for func in dependency_functions:
            if not self.__definition_is_allowed_for(func, environment):
                continue

            key = self.__provider_key_for_definition(func)

            if key is not None:
                leaf_map[key] = func

        provider_keys = {
            Request,
            Locale,
            I18n,
            Principal,
            WebSocket,
            *(
                service_class
                for service_class in service_classes
                if self.__definition_is_allowed_for(service_class, environment)
            ),
            *(
                configuration_class
                for configuration_class in configuration_classes
                if self.__definition_is_allowed_for(configuration_class, environment)
            ),
            *leaf_map.keys()
        }

        return provider_keys, leaf_map

    def __environment_dependency_error(
        self,
        key: Any,
        *,
        environment: Environment,
        consumer: Any,
        provider_keys: set[Any],
        leaf_map: dict[Any, Callable[..., Any]],
        stack: tuple[Any, ...]
    ) -> str | None:
        if is_union_dependency(key):
            candidates = union_dependency_args(key)
            environment_sets = {
                candidate: self.__dependency_environment_set(candidate, leaf_map)
                for candidate in candidates
            }
            active_candidates = tuple(
                candidate
                for candidate in candidates
                if environment in environment_sets[candidate]
            )

            if not active_candidates:
                candidate_names = ' | '.join(self.__dependency_key_name(candidate) for candidate in candidates)
                return (
                    f'{self.__dependency_consumer_name(consumer)} requires {candidate_names}, '
                    f'but no union dependency is active for {environment.value}'
                )

            for candidate in active_candidates:
                error = self.__environment_dependency_error(
                    candidate,
                    environment = environment,
                    consumer = consumer,
                    provider_keys = provider_keys,
                    leaf_map = leaf_map,
                    stack = stack
                )

                if error is not None:
                    return error

            return None

        if key in (Request, Locale, I18n, Principal, WebSocket) or key in self.__configuration_classes:
            return None

        if key not in provider_keys:
            definition = self.__provider_definitions.get(key, leaf_map.get(key, key))
            allowed_on = self.__only_environments_for(definition)

            if allowed_on is not None and environment not in allowed_on:
                allowed = ', '.join(self.__environment_label(item) for item in allowed_on)
                return (
                    f'{self.__dependency_consumer_name(consumer)} requires {self.__dependency_key_name(key)}, '
                    f'but it is only allowed on {allowed}'
                )

            return (
                f'{self.__dependency_consumer_name(consumer)} requires {self.__dependency_key_name(key)}, '
                f'but no provider is registered for {environment.value}'
            )

        if key in stack:
            return None

        definition = self.__provider_definitions.get(key, leaf_map.get(key, key))
        provider_meta = getattr(definition, '__autumn_provider__', None)

        if inspect.isclass(definition) and provider_meta and provider_meta[0] == 'class':
            callable = definition.__init__
            dependencies = self.__callable_dependency_keys(
                callable,
                skip_self = True,
                provider_keys = provider_keys,
                can_resolve_dependency = lambda dependency: self.__dependency_key_available_for_environment(dependency, provider_keys)
            )

        elif key in leaf_map:
            callable = leaf_map[key]
            dependencies = self.__callable_dependency_keys(
                callable,
                provider_keys = provider_keys,
                can_resolve_dependency = lambda dependency: self.__dependency_key_available_for_environment(dependency, provider_keys)
            )

        else:
            return None

        for dependency in dependencies:
            error = self.__environment_dependency_error(
                dependency,
                environment = environment,
                consumer = callable,
                provider_keys = provider_keys,
                leaf_map = leaf_map,
                stack = (*stack, key)
            )

            if error is not None:
                return error

        return None

    def __warn_about_inactive_environment_dependency_graphs(self) -> None:
        (
            _,
            _,
            dependency_functions,
            service_classes,
            configuration_classes,
            *_rest
        ) = dependency_registry.registered_definitions()

        dependency_functions = tuple(dependency_functions)
        service_classes = tuple(service_classes)
        configuration_classes = tuple(configuration_classes)

        for environment in Environment:
            if environment == self.environment:
                continue

            provider_keys, leaf_map = self.__provider_keys_for_environment(
                environment,
                dependency_functions,
                service_classes,
                configuration_classes
            )

            active_service_classes = tuple(
                service_class
                for service_class in service_classes
                if self.__definition_is_allowed_for(service_class, environment)
            )

            for provider_key in (*active_service_classes, *leaf_map.keys()):
                error = self.__environment_dependency_error(
                    provider_key,
                    environment = environment,
                    consumer = provider_key,
                    provider_keys = provider_keys,
                    leaf_map = leaf_map,
                    stack = ()
                )

                if error is None:
                    continue

                warning = (
                    f'@only dependency graph warning for {environment.value}: {error}. '
                    f'This application can start on {self.environment.value}, but may fail on {environment.value}.'
                )

                if warning in self.__environment_dependency_warnings:
                    continue

                self.__environment_dependency_warnings.add(warning)
                self.__warn(warning)

    def __normalize_response(self, result, handler_callable) -> Response:
        if isinstance(result, Response):
            return result

        if getattr(handler_callable, '__json_response__', False) or value_supports_json_response(result):
            return JSONResponse(result)

        raise TypeError(f'Handler returned unsupported result type: {type(result).__name__}')

    def __resolve_request_id(self, request: Request) -> str:
        request_id = (
            request.header('x-request-id')
            or request.header('x-correlation-id')
            or uuid4().hex
        )
        request.request_id = request_id
        return request_id

    def __configure_i18n_context(self, request: Request, context: ExecutionContext) -> None:
        configuration = self.__localization_configuration or LocalizationConfiguration.build()
        supported_locales = tuple(str(locale) for locale in configuration.supported_locales)
        default_locale = str(configuration.default_locale)

        if default_locale not in supported_locales:
            supported_locales = (*supported_locales, default_locale)

        locale_code = select_locale(
            request,
            supported_locales = supported_locales,
            default_locale = default_locale,
            header = configuration.source_header
        )
        locale = Locale(locale_code)
        i18n = I18n(
            locale,
            load_locale_messages(configuration.locales, locale_code),
            configuration.plural_rules
        )

        request.locale = locale
        request.i18n = i18n
        context.values[Locale] = locale
        context.values[I18n] = i18n

    def __internal_error_details(self, error: Exception) -> str:
        if self.environment == Environment.PRODUCTION:
            return 'Internal Server Error'

        return str(error)

    @staticmethod
    def __copy_handler_metadata(source: Callable, target: Callable) -> Callable:
        for attribute in ('__query_parameters__', '__body_schema__', '__json_response__', '__response_model__'):
            if hasattr(source, attribute):
                setattr(target, attribute, getattr(source, attribute))

        return target

    @staticmethod
    def __resolve_query_kwargs(request: Request, query_meta: list[dict]) -> dict[str, object]:
        raw_query = request.query.__dict__ if hasattr(request.query, '__dict__') else request.query
        parsed: dict[str, object] = {}

        for parameter in query_meta:
            name     = parameter.get('name')
            cast     = parameter.get('type')
            required = parameter.get('required')
            default  = parameter.get('default')

            raw_value = raw_query.get(name)

            if raw_value is None:
                if required:
                    raise HTTPException(
                        status  = 400,
                        details = f'Missing query parameter: \'{name}\''
                    )

                if default is not None:
                    parsed[name] = default
                else:
                    parsed[name] = None

                continue

            try:
                parsed[name] = cast(raw_value)

            except Exception:
                raise HTTPException(
                    status = 400,
                    details = f'Invalid value for \'{name}\''
                )

        request.query = parsed
        return parsed

    @staticmethod
    def __get_controller_middleware_metadata(controller_class: type) -> dict[str, tuple[str, ...]]:
        cached = getattr(controller_class, '__autumn_controller_middlewares__', None)

        if cached is not None:
            return cached

        around: list[str] = []
        before: list[str] = []
        after: list[str] = []

        for name, attribute in controller_class.__dict__.items():
            metadata = getattr(attribute, '__controller_middleware__', None)

            if metadata is None:
                continue

            kind = metadata.get('kind', 'around')

            if kind == 'around':
                if not (inspect.isgeneratorfunction(attribute) or inspect.isasyncgenfunction(attribute)):
                    raise TypeError(
                        f'Controller middleware \'{controller_class.__name__}.{name}\' must yield exactly once'
                    )

                around.append(name)
                continue

            if kind == 'before':
                before.append(name)
                continue

            if kind == 'after':
                after.append(name)
                continue

            raise TypeError(f'Unknown controller middleware kind: {kind}')

        cached = {
            'around' : tuple(around),
            'before' : tuple(before),
            'after'  : tuple(after)
        }
        setattr(controller_class, '__autumn_controller_middlewares__', cached)

        return cached

    @staticmethod
    def __controller_call_kwargs(
        request: Request,
        path_parameters: dict[str, Any],
        *,
        response: Optional[Response] = None
    ) -> dict[str, Any]:
        kwargs = {
            **path_parameters,
            'request': request
        }

        if response is not None:
            kwargs['response'] = response

        return kwargs

    async def __run_controller_before_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> None:
        await self.container.call(
            getattr(controller, middleware_name),
            context = context,
            provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
        )

    async def __run_controller_after_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        response: Response,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> Response:
        result = await self.container.call(
            getattr(controller, middleware_name),
            context = context,
            provided_kwargs = self.__controller_call_kwargs(
                request,
                path_parameters,
                response = response
            )
        )

        if isinstance(result, Response):
            return result

        return response

    async def __enter_controller_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> tuple[str, Any, str]:
        middleware_callable = getattr(controller, middleware_name)
        kwargs = await self.container.resolve_call_kwargs(
            middleware_callable,
            context = context,
            provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
        )
        generator = middleware_callable(**kwargs)

        if inspect.isasyncgen(generator):
            try:
                await anext(generator)

            except StopAsyncIteration as error:
                raise RuntimeError(
                    f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must yield exactly once'
                ) from error

            return ('async', generator, middleware_name)

        if inspect.isgenerator(generator):
            try:
                next(generator)

            except StopIteration as error:
                raise RuntimeError(
                    f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must yield exactly once'
                ) from error

            return ('sync', generator, middleware_name)

        raise TypeError(
            f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must be a generator'
        )

    @staticmethod
    async def __close_controller_middleware(state: tuple[str, Any, str]) -> None:
        mode, generator, _ = state

        if mode == 'async':
            await generator.aclose()
            return

        generator.close()

    async def __exit_controller_middleware(
        self,
        state: tuple[str, Any, str],
        response: Response,
        *,
        controller_name: str
    ) -> Response:
        mode, generator, middleware_name = state

        if mode == 'async':
            try:
                await generator.asend(response)

            except StopAsyncIteration:
                return response

            raise RuntimeError(
                f'Controller middleware \'{controller_name}.{middleware_name}\' must yield exactly once'
            )

        try:
            generator.send(response)

        except StopIteration as stop:
            if isinstance(stop.value, Response):
                return stop.value

            return response

        raise RuntimeError(
            f'Controller middleware \'{controller_name}.{middleware_name}\' must yield exactly once'
        )

    def __get_http_handler_callable(self, handler: tuple[type, str]) -> Callable:
        if handler in self.__http_handler_cache:
            return self.__http_handler_cache[handler]

        controller_class, method_name = handler
        original_method = getattr(controller_class, method_name)
        controller_middlewares = self.__get_controller_middleware_metadata(controller_class)

        async def endpoint(request: Request, **path_parameters):
            context = getattr(request, '_autumn_execution_context', None)

            controller = await self.container.resolve(controller_class, context)
            method = getattr(controller, method_name)
            active_middlewares: list[tuple[str, Any, str]] = []

            try:
                for middleware_name in controller_middlewares['around']:
                    active_middlewares.append(
                        await self.__enter_controller_middleware(
                            controller,
                            middleware_name,
                            request = request,
                            context = context,
                            path_parameters = path_parameters
                        )
                    )

                for middleware_name in controller_middlewares['before']:
                    await self.__run_controller_before_middleware(
                        controller,
                        middleware_name,
                        request = request,
                        context = context,
                        path_parameters = path_parameters
                    )

                response = self.__normalize_response(
                    await self.container.call(
                        method,
                        context = context,
                        provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
                    ),
                    original_method
                )

                for middleware_name in controller_middlewares['after']:
                    response = await self.__run_controller_after_middleware(
                        controller,
                        middleware_name,
                        request = request,
                        response = response,
                        context = context,
                        path_parameters = path_parameters
                    )

            except Exception:
                for state in reversed(active_middlewares):
                    await self.__close_controller_middleware(state)

                raise

            for state in reversed(active_middlewares):
                response = await self.__exit_controller_middleware(
                    state,
                    response,
                    controller_name = controller_class.__name__
                )

            return response

        cached = self.__copy_handler_metadata(original_method, endpoint)
        cached.__autumn_controller_endpoint__ = True
        self.__http_handler_cache[handler] = cached

        return cached

    def __get_websocket_handler_callable(self, handler: tuple[type, str]) -> Callable:
        if handler in self.__websocket_handler_cache:
            return self.__websocket_handler_cache[handler]

        controller_class, method_name = handler

        async def endpoint(websocket: WebSocket, **path_parameters):
            context = getattr(websocket, '_autumn_execution_context', None)

            controller = await self.container.resolve(controller_class, context)
            method = getattr(controller, method_name)

            return await self.container.call(
                method,
                context = context,
                provided_kwargs = {
                    **path_parameters,
                    'websocket': websocket
                }
            )

        self.__websocket_handler_cache[handler] = endpoint
        return endpoint

    async def __invoke_http_execution_plan(
        self,
        plan: HTTPExecutionPlan,
        current_request: Request,
        original_request: Request,
        context: ExecutionContext,
        provided_kwargs: dict[str, Any]
    ) -> Response:
        current_kwargs = provided_kwargs

        if current_request is not original_request:
            current_kwargs = {
                **provided_kwargs,
                'request': current_request
            }

        if plan.is_controller:
            result = await plan.handler_callable(
                current_request,
                **{
                    key: value
                    for key, value in current_kwargs.items()
                    if key != 'request'
                }
            )
        else:
            result = await self.container.call(
                plan.handler_callable,
                context = context,
                provided_kwargs = current_kwargs
            )

        return self.__normalize_response(result, plan.handler_callable)

    async def __authenticate_request(self, request: Request) -> Principal:
        configuration = self.__security_configuration

        if configuration is None:
            return AnonymousPrincipal()

        for scheme in configuration.schemes:
            principal = await scheme.authenticate(request)

            if principal is not None:
                if not isinstance(principal, Principal) or not principal.authenticated:
                    raise TypeError('Authentication schemes must return an authenticated Principal or None')

                return principal

        return AnonymousPrincipal()

    async def __authorize_request(
        self,
        plan: HTTPExecutionPlan,
        request: Request,
        context: ExecutionContext,
        provided_kwargs: dict[str, Any]
    ) -> None:
        requirements = plan.security
        principal: Principal = AnonymousPrincipal()
        context.values[Principal] = principal
        request.principal = principal

        if requirements.public or not requirements.required:
            return

        principal = await self.__authenticate_request(request)
        context.values[Principal] = principal
        request.principal = principal

        if not principal.authenticated:
            configuration = self.__security_configuration
            challenge = (
                configuration.schemes[0].challenge
                if configuration is not None and configuration.schemes
                else 'Bearer'
            )
            raise HTTPException(
                status = 401,
                details = 'Authentication required',
                headers = {'WWW-Authenticate': challenge}
            )

        if requirements.roles and requirements.roles.isdisjoint(principal.roles):
            raise HTTPException(status = 403, details = 'Access denied')

        if not requirements.permissions.issubset(principal.permissions):
            raise HTTPException(status = 403, details = 'Access denied')

        for policy_name in requirements.policies:
            policy_callable = get_policy(policy_name)
            allowed = await self.container.call(
                policy_callable,
                context = context,
                provided_kwargs = provided_kwargs
            )

            if allowed is not True:
                raise HTTPException(status = 403, details = 'Access denied')

    @staticmethod
    async def __send_response(send, response: Response) -> None:
        await send({
            'type'    : 'http.response.start',
            'status'  : response.status,
            'headers' : response.headers_as_list(),
        })

        if hasattr(response, 'body_iterate') and callable(getattr(response, 'body_iterate')):
            async for chunk in response.body_iterate():
                await send({
                    'type'      : 'http.response.body',
                    'body'      : chunk,
                    'more_body' : True
                })

            await send({
                'type'      : 'http.response.body',
                'body'      : b'',
                'more_body' : False
            })
            
            return

        await send({
            'type'      : 'http.response.body',
            'body'      : response.body_as_bytes(),
            'more_body' : False
        })

    @staticmethod
    def __normalize_header_values(values) -> list[str]:
        if values is None:
            return []

        return [
            str(value).strip()
            for value in values
            if str(value).strip()
        ]

    @staticmethod
    def __merge_vary(current: Optional[str], *values: str) -> Optional[str]:
        merged: list[str] = []

        for chunk in (current, *values):
            if not chunk:
                continue

            for item in str(chunk).split(','):
                normalized = item.strip()

                if normalized and normalized not in merged:
                    merged.append(normalized)

        if not merged:
            return None

        return ', '.join(merged)

    def __is_cors_preflight(self, request: Request) -> bool:
        if self.__cors_configuration is None or not self.__cors_configuration.enabled:
            return False

        return (
            request.method == 'OPTIONS'
            and bool(request.header('origin'))
            and bool(request.header('access-control-request-method'))
        )

    def __is_cors_origin_allowed(self, origin: str) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_origins = self.__normalize_header_values(configuration.allowed_origins)

        return '*' in allowed_origins or origin in allowed_origins

    def __is_cors_method_allowed(self, method: str) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_methods = [
            value.upper()
            for value in self.__normalize_header_values(configuration.allowed_methods)
        ]

        return '*' in allowed_methods or method.upper() in allowed_methods

    def __is_cors_headers_allowed(self, requested_headers: list[str]) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_headers = [
            value.lower()
            for value in self.__normalize_header_values(configuration.allowed_headers)
        ]

        if '*' in allowed_headers:
            return True

        return all(header.lower() in allowed_headers for header in requested_headers)

    def __build_cors_headers(self, request: Request, *, preflight: bool = False) -> dict[str, str]:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return {}

        origin = request.header('origin')

        if not origin or not self.__is_cors_origin_allowed(origin):
            if preflight and origin:
                raise HTTPException(
                    status = 403,
                    details = 'CORS origin is not allowed'
                )

            return {}

        allowed_origins = self.__normalize_header_values(configuration.allowed_origins)
        allow_any_origin = '*' in allowed_origins

        headers: dict[str, str] = {
            'Access-Control-Allow-Origin': (
                '*' 
                if allow_any_origin and not configuration.allow_credentials 
                else origin
            )
        }

        vary = None if headers['Access-Control-Allow-Origin'] == '*' else 'Origin'

        if configuration.allow_credentials:
            headers['Access-Control-Allow-Credentials'] = 'true'

        expose_headers = self.__normalize_header_values(configuration.expose_headers)

        if expose_headers and not preflight:
            headers['Access-Control-Expose-Headers'] = ', '.join(expose_headers)

        if preflight:
            requested_method = (request.header('access-control-request-method') or '').upper()

            if not requested_method or not self.__is_cors_method_allowed(requested_method):
                raise HTTPException(
                    status = 405,
                    details = 'CORS method is not allowed'
                )

            allowed_methods = [
                value.upper()
                for value in self.__normalize_header_values(configuration.allowed_methods)
            ]

            headers['Access-Control-Allow-Methods'] = ', '.join(
                [requested_method]
                if '*' in allowed_methods
                else allowed_methods
            )

            requested_headers_raw = request.header('access-control-request-headers') or ''
            requested_headers = [
                header.strip()
                for header in requested_headers_raw.split(',')
                if header.strip()
            ]

            if requested_headers and not self.__is_cors_headers_allowed(requested_headers):
                raise HTTPException(
                    status = 400,
                    details = 'CORS headers are not allowed'
                )

            allowed_headers = self.__normalize_header_values(configuration.allowed_headers)

            if requested_headers_raw:
                headers['Access-Control-Allow-Headers'] = (
                    requested_headers_raw
                    if '*' in [value.lower() for value in allowed_headers]
                    else ', '.join(allowed_headers)
                )

            elif allowed_headers:
                headers['Access-Control-Allow-Headers'] = ', '.join(allowed_headers)

            headers['Access-Control-Max-Age'] = str(configuration.max_age)
            vary = self.__merge_vary(vary, 'Access-Control-Request-Method', 'Access-Control-Request-Headers')

        if vary is not None:
            headers['Vary'] = vary

        return headers

    def __apply_response_headers(self, response: Response, headers: dict[str, str]) -> Response:
        if not headers:
            return response

        for key, value in headers.items():
            if key.lower() == 'vary':
                response.headers['Vary'] = self.__merge_vary(response.headers.get('Vary'), value) or value
                continue

            response.headers[key] = value

        return response

    async def __lifespan(self, scope, receive, send):
        if scope['type'] != 'lifespan':
            return
        
        while True:
            message = await receive()

            if message['type'] == 'lifespan.startup':
                try:
                    start = time.perf_counter()

                    self.__sync_providers()
                    await asyncio.gather(*(hook() for hook in self.startup_hooks))

                    duration = (time.perf_counter() - start) * 1000

                    print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + Fore.GREEN + f'Startup completed in {duration:.2f}ms' + Fore.RESET)

                    await send({ 'type' : 'lifespan.startup.complete' })
                
                except Exception as error:
                    await send({ 
                        'type' : 'lifespan.startup.failed', 
                        'message' : str(error) 
                    })
                    raise

            elif message['type'] == 'lifespan.shutdown':
                try:
                    start = time.perf_counter()

                    await asyncio.gather(*(hook() for hook in self.shutdown_hooks))

                    duration = (time.perf_counter() - start) * 1000

                    print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + Fore.GREEN + f'Shutdown completed in {duration:.2f}ms' + Fore.RESET)

                    await send({ 'type' : 'lifespan.shutdown.complete' })
                    return
                
                except Exception as error:
                    await send({ 
                        'type' : 'lifespan.shutdown.failed', 
                        'message' : str(error) 
                    })
                    raise


    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            await self.__lifespan(scope, receive, send)
            return

        self.__sync_providers()
		
        if scope['type'] == 'websocket':
            websocket: WebSocket = WebSocket(scope, receive, send)
            websocket.app = self

            match = self.router.match_websocket(scope['path'])

            try:
                if match is None:
                    await websocket.close(code = 1000)
                    return
                
                handler = match.handler
                parameters = match.parameters

                context = ExecutionContext()
                context.values[WebSocket] = websocket
                websocket._autumn_execution_context = context

                if isinstance(handler, tuple) and (len(handler) == 2) and isinstance(handler[1], str):
                    handler_callable = self.__get_websocket_handler_callable(handler)

                else:
                    handler_callable = handler

                await self.container.call(
                    handler_callable,
                    context         = context,
                    provided_kwargs = { 
                        **parameters,
                        'websocket': websocket 
                    }
                )
            
            except WebSocketDisconnect:
                return
            
            except Exception as error:
                if self.environment != Environment.PRODUCTION:
                    print(error)
                try:
                    await websocket.close(code = 1011)

                except Exception:
                    pass
                
                return

            return

        if scope['type'] != 'http':
            raise NotImplementedError(f'Unsupported scope type: {scope['type']}')

        assert scope['type'] == 'http'

        request = Request(
            scope,
            receive,
            max_body_bytes = (
                self.__application_configuration.max_request_body_bytes
                if self.__application_configuration is not None
                else 1024 * 1024
            )
        )
        request.app = self
        request_id = self.__resolve_request_id(request)

        if self.__is_cors_preflight(request):
            try:
                response = Response(
                    body = '',
                    status = 204,
                    headers = {
                        'X-Request-ID': request_id,
                        **self.__build_cors_headers(request, preflight = True)
                    }
                )

            except HTTPException as error:
                response = error.to_response(request)

            except Exception as error:
                if self.environment != Environment.PRODUCTION:
                    print(error)
                response = HTTPException(
                    status = 500,
                    details = self.__internal_error_details(error)
                ).to_response(request)

            await self.__send_response(send, response)
            return

        match = self.router.match(scope['method'], scope['path'])

        try:
            if match is None:
                raise HTTPException(
                    status = 404, 
                    details = f'Route {scope.get('path')} not found'
                )
        
            parameters = match.parameters

            context = ExecutionContext()
            context.values[Request] = request
            request._autumn_execution_context = context
            self.__configure_i18n_context(request, context)

            plan = match.route.execution_plan

            if plan is None:
                raise RuntimeError(
                    f'HTTP execution plan was not compiled for {match.route.path_template}'
                )

            provided_kwargs = {
                **parameters,
                'request': request
            }

            if plan.query_metadata:
                provided_kwargs.update(
                    self.__resolve_query_kwargs(request, plan.query_metadata)
                )

            await self.__authorize_request(
                plan,
                request,
                context,
                provided_kwargs
            )

            if plan.middleware.is_empty:
                response = await self.__invoke_http_execution_plan(
                    plan,
                    request,
                    request,
                    context,
                    provided_kwargs
                )
            else:
                async def invoke(current_request: Request) -> Response:
                    return await self.__invoke_http_execution_plan(
                        plan,
                        current_request,
                        request,
                        context,
                        provided_kwargs
                    )

                response = self.__normalize_response(
                    await plan.middleware.execute(invoke, request),
                    plan.handler_callable
                )

        except HTTPException as error:
            response = error.to_response(request)

        except Exception as error:
            if self.environment != Environment.PRODUCTION:
                print(error)

            response = HTTPException(
                status = 500, 
                details = self.__internal_error_details(error)
            ).to_response(request)

        response = self.__apply_response_headers(
            response,
            self.__build_cors_headers(request)
        )
        response.headers.setdefault('X-Request-ID', request_id)
        
        await self.__send_response(send, response)
