from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from autumn.cli.environment.engine.models import EnvironmentConfig, EnvironmentType, PythonConfig, ApplicationConfig, ServerConfig, IndexesConfig
from autumn.cli.environment.engine.paths import AutumnPaths
from autumn.cli.environment.engine.repositories import EnvironmentRepository, ActiveEnvironmentRepository
from autumn.cli.environment.engine.schema import SchemaExporter
from autumn.cli.environment.engine.context import EnvironmentContextLoader
from autumn.cli.environment.engine.doctor import DoctorService
from autumn.cli.environment.engine.ui import UI


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
    type    = click.Choice([e.value for e in EnvironmentType]), 
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

    repository.write(paths.env_json_path(name), config)

    SchemaExporter(paths.schemas_directory).export_environment_schema()

    Console().print(f'[green]Created[/green] {paths.environment_json_path(name)}')


@click.command('use')
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

    repository = EnvironmentRepository(paths.environments_dir)
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
    help    = 'Strict mode (lock required). Not implemented yet in this initial step.'
)
def install_command(environment_name: Optional[str], groups: str, frozen: bool) -> None:
    if frozen:
        raise click.ClickException('--frozen requires lock implementation (next step).')

    paths = __paths_from_env()
    loader = EnvironmentContextLoader(paths)
    resolved = loader.resolve_env_name(environment_name)
    context = loader.load(resolved)

    ui = Console()

    for warning in context.dotenv.warnings:
        ui.print(f'[yellow]WARNING[/yellow] {warning}')

    requirements = loader.build_requirements(context.config, __split_groups(groups))

    if not requirements:
        ui.print('[yellow]WARNING[/yellow] No requirements to install for selected groups.')
        return

    pip = loader.build_pip(context)
    indexes = loader.build_indexes(context.config)

    ui.print(f'Installing into [bold]{context.environment_name}[/bold] venv...')
    
    pip.install(
        requirements, 
        indexes = indexes, 
        upgrade = False
    )
    
    ui.print('[green]Done.[/green]')


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
