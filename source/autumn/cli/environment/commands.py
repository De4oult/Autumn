from __future__ import annotations

from autumn.cli.environment.engine.models import EnvironmentConfig, EnvironmentType, PythonConfig, ApplicationConfig, ServerConfig, IndexesConfig, LockFile, LockGroup
from autumn.cli.environment.engine.paths import AutumnPaths
from autumn.cli.environment.engine.repositories import EnvironmentRepository, ActiveEnvironmentRepository, LockRepository
from autumn.cli.environment.engine.schema import SchemaExporter
from autumn.cli.environment.engine.context import EnvironmentContextLoader
from autumn.cli.environment.engine.doctor import DoctorService
from autumn.cli.environment.engine.ui import UI
from autumn.cli.environment.engine.lock import LockBuilder, _normalize_requested
from autumn.cli.environment.engine.pip import RequirementsBuilder, PipIndexes
from autumn.cli.environment.engine.frozen import build_frozen_requirements_file, FrozenLockError

from pathlib import Path
from typing import Optional, List
from rich.console import Console

import subprocess
import click
import os


def __paths_from_env() -> AutumnPaths:
    root = os.environ.get('AUTUMN_PROJECT_ROOT', '.')

    return AutumnPaths(project_root = Path(root).resolve())


def __split_groups(groups: str) -> list[str]:
    return [group.strip() for group in groups.split(',') if group.strip()]


@click.group()
def environment_group() -> None:
    ...


@environment_group.command('list')
def env_list() -> None:
    paths = __paths_from_env()
    repository = EnvironmentRepository(paths.environments_directory)
    active_repository = ActiveEnvironmentRepository(paths.active_env_file)

    ui = UI(Console())
    ui.env_list(
        repository.list_names(), 
        active_repository.get()
    )


@environment_group.command('create')
@click.argument('name', type=str)
@click.option(
    '--type', 
    'environment_type', 
    type    = click.Choice([environment_type.value for environment_type in EnvironmentType]), 
    default = EnvironmentType.LOCAL.value
)
@click.option(
    '--python', 
    'python_version', 
    type    = str, 
    default = '3.12'
)
@click.option(
    '--app-name', 
    type    = str, 
    default = 'autumn_application'
)
@click.option(
    '--app-module', 
    type    = str, 
    default = 'my_app.main:app'
)
def env_create(name: str, environment_type: str, python_version: str, app_name: str, app_module: str) -> None:
    paths = __paths_from_env()
    repository = EnvironmentRepository(paths.environments_directory)

    if repository.exists(name):
        raise click.ClickException(f'Environment already exists: {name}')

    config = EnvironmentConfig(
        name    = name,
        type    = EnvironmentType(environment_type),
        python  = PythonConfig(version = python_version),
        indexes = IndexesConfig(),
        app     = ApplicationConfig(
            name    = app_name, 
            module  = app_module, 
            version = '0.1.0'
        ),
        server  = ServerConfig(
            host    = '127.0.0.1',
            port    = 8000,
            reload  = (environment_type in (EnvironmentType.LOCAL.value, EnvironmentType.DEVELOPMENT.value)),
            workers = 1
        ),
        dependencies = {
            'default': {}, 
            'dev': {}
        },
        plugins = {}
    )

    repository.write(paths.environment_json_path(name), config)

    SchemaExporter(paths.schemas_directory).export_environment_schema()

    Console().print(f'[green]Created[/green] {paths.environment_json_path(name)}')


@environment_group.command('use')
@click.argument('name', type = str)
def use_command(name: str) -> None:
    paths = __paths_from_env()
    repository = EnvironmentRepository(paths.environments_directory)
    active_repository = ActiveEnvironmentRepository(paths.active_env_file)

    if not repository.exists(name):
        raise click.ClickException(f'Environment not found: {name}')

    active_repository.set(name)

    Console().print(f'[green]Active environment:[/green] {name}')


@environment_group.command('show')
@click.argument('name', type = str)
@click.option('--json', 'as_json', is_flag = True, default = False)
def env_show(name: str, as_json: bool) -> None:
    paths = __paths_from_env()

    repository = EnvironmentRepository(paths.environments_directory)
    path = paths.environment_json_path(name)
    
    if not path.exists():
        raise click.ClickException(f'Not found: {path}')
    
    config = repository.read(path)

    if as_json:
        Console().print(
            config.model_dump_json(
                indent = 4, 
                exclude_none = True
            )
        )

    else:
        Console().print(f'[bold]{config.name}[/bold] ({config.type})')
        Console().print(f'Python: {config.python.version}')
        Console().print(f'App: {config.app.module}')
        Console().print(f'Server: {config.server.host}:{config.server.port} reload={config.server.reload} workers={config.server.workers}')
        Console().print(f'Groups: {', '.join(sorted(config.dependencies.keys()))}')


@click.command('install')
@click.option(
    '--environment', 
    'environment_name', 
    type    = str, 
    default = None
)
@click.option(
    '--groups', 
    type    = str, 
    default = 'default', 
    help    = 'Comma-separated groups: default,dev'
)
@click.option(
    '--frozen', 
    is_flag = True, 
    default = False, 
    help    = 'Strict mode: install exactly from lock and refuse drift.'
)
def install_command(environment_name: Optional[str], groups: str, frozen: bool) -> None:
    paths = __paths_from_env()
    loader = EnvironmentContextLoader(paths)
    resolved = loader.resolve_env_name(environment_name)
    context = loader.load(resolved)

    console = Console()

    for warning in context.dotenv.warnings:
        console.print(f"[yellow]WARN[/yellow] {warning}")

    config = context.config
    indexes = loader.build_indexes(config)
    pip = loader.build_pip(context)

    selected_groups = __split_groups(groups)

    if frozen:
        lock_path = paths.lock_json_path(context.env_name)
        lock_repo = LockRepository(lock_path)

        if not lock_repo.exists():
            raise click.ClickException(f'Lock file not found: {lock_path}. Run: autumn lock')

        lock = lock_repo.read()

        if lock.environment != context.env_name:
            raise click.ClickException('Lock environment mismatch.')
        
        if lock.python != config.python.version:
            raise click.ClickException(f'Python mismatch: env.json={config.python.version}, lock={lock.python}')

        rb = RequirementsBuilder()

        for group in selected_groups:
            requested_now = sorted({_normalize_requested(r) for r in rb.build(config, [group]) if r})

            if group not in lock.groups:
                raise click.ClickException(f'Group \'{group}\' is missing in lock. Re-run: autumn lock --groups {group}')
            
            requested_lock = lock.groups[group].requested

            if requested_now != requested_lock:
                raise click.ClickException(f'Requested deps drift for group \'{group}\'. Re-run: autumn lock --groups {group}')

        try:
            req_file, pool_dir = build_frozen_requirements_file(
                lock=lock,
                paths=context.paths,
                env_name=context.env_name,
                groups=selected_groups,
            )
        except FrozenLockError as e:
            raise click.ClickException(str(e))

        console.print(f'Frozen install (no-index, require-hashes) into [bold]{context.env_name}[/bold] venv...')
        console.print(f'Using artifacts from: {pool_dir}')
        console.print(f'Using requirements: {req_file}')

        pip.install_from_file(
            requirements_file=req_file,
            indexes=None,
            require_hashes=True,
            no_deps=True,
            no_index=True,
            find_links=[pool_dir],
        )

        console.print('[green]Done.[/green]')
        return

    requirements = loader.build_requirements(config, selected_groups)

    if not requirements:
        console.print('[yellow]WARN[/yellow] No requirements to install for selected groups.')
        return

    console.print(f'Installing into [bold]{context.env_name}[/bold] venv...')

    pip.install(
        requirements, 
        indexes = indexes, 
        upgrade = False
    )

    console.print('[green]Done.[/green]')


@click.command('serve')
@click.option(
    '--environment', 
    'environment_name', 
    type    = str, 
    default = None
)
@click.option(
    '--reload', 
    is_flag = True, 
    default = None
)
@click.option(
    '--host', 
    type    = str, 
    default = None
)
@click.option(
    '--port', 
    type    = int, 
    default = None
)
def serve_command(environment_name: Optional[str], reload: Optional[bool], host: Optional[str], port: Optional[int]) -> None:
    paths = __paths_from_env()
    loader = EnvironmentContextLoader(paths)
    resolved = loader.resolve_env_name(environment_name)
    context = loader.load(resolved)

    console = Console()
    for warning in context.dotenv.warnings:
        console.print(f'[yellow]WARNING[/yellow] {warning}')

    config = context.config
    run_reload = config.server.reload if reload is None else reload
    run_host   = config.server.host if host is None else host
    run_port   = config.server.port if port is None else port

    python = context.venv.python_exe()
    cmd = [
        str(python),
        '-m',
        'uvicorn',
        config.app.module,
        '--host',
        str(run_host),
        '--port',
        str(run_port),
    ]

    if run_reload:
        cmd.append('--reload')

    if config.server.workers and config.server.workers > 1 and not run_reload:
        cmd += ['--workers', str(config.server.workers)]

    console.print(f'Running: [bold]{' '.join(cmd)}[/bold]')
    subprocess.check_call(cmd)


@click.command('doctor')
@click.option(
    '--environment', 
    'environment_name', 
    type    = str, 
    default = None
)
def doctor_command(environment_name: Optional[str]) -> None:
    paths = __paths_from_env()
    loader = EnvironmentContextLoader(paths)
    resolved = loader.resolve_env_name(environment_name)
    context = loader.load(resolved)

    service = DoctorService()
    issues = service.check(context)

    UI(Console()).doctor(issues)


@click.command('lock')
@click.option(
    '--environment', 
    'environment_name', 
    type    = str, 
    default = None
)
@click.option(
    '--groups', 
    type    = str, 
    default = '', 
    help    = 'Comma-separated groups. Empty = all groups from env.json'
)
def lock_command(environment_name: Optional[str], groups: str) -> None:
    paths = __paths_from_env()
    loader = EnvironmentContextLoader(paths)
    resolved = loader.resolve_env_name(environment_name)
    context = loader.load(resolved)

    console = Console()

    for warning in context.dotenv.warnings:
        console.print(f"[yellow]WARNING[/yellow] {warning}")

    config = context.config
    indexes = loader.build_indexes(config)
    pip = loader.build_pip(context)

    target_groups = __split_groups(groups) if groups.strip() else sorted(config.dependencies.keys())

    lock_repo = LockRepository(paths.lock_json_path(context.env_name))

    if lock_repo.exists():
        lock = lock_repo.read()
        lock.environment = context.env_name
        lock.python = config.python.version
        lock.indexes = config.indexes

    else:
        lock = LockFile(
            environment = context.env_name,
            python      = config.python.version,
            indexes     = config.indexes,
            groups      = {}
        )

    builder = LockBuilder(RequirementsBuilder())
    updates = {}

    console.print(f'Locking env [bold]{context.env_name}[/bold] groups: {', '.join(target_groups)}')

    for group in target_groups:
        updates[group] = builder.build_group_lock(
            config,
            group,
            indexes=indexes,
            paths=context.paths,
            env_name=context.env_name,
            python_version=config.python.version,
        )

    lock = builder.merge_groups(lock, updates)
    lock_repo.write(lock)

    console.print(f'[green]Wrote lock:[/green] {paths.lock_json_path(context.env_name)}')
