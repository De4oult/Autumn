from __future__ import annotations

import click
from rich.console import Console

from autumn.cli.manager.core.filesystem import FileSystem
from autumn.cli.commands import CommandRegistry
from autumn.cli.console import AutumnConsole

from autumn.cli.manager.commands.create_configuration import CreateConfigurationCommand
from autumn.cli.manager.commands.create_controller import CreateControllerCommand
from autumn.cli.manager.commands.create_project import CreateProjectCommand


def initialize_cli() -> click.Group:
    file_system = FileSystem()
    out = AutumnConsole(Console())

    registry = CommandRegistry(
        commands = [
            CreateProjectCommand(
                file_system = file_system, 
                out         = out
            ),
            CreateConfigurationCommand(
                file_system = file_system, 
                out         = out
            ),
            CreateControllerCommand(
                file_system = file_system,
                out         = out
            )
        ]
    )

    @click.group(name = 'autumn')
    def root() -> None:
        ...

    registry.attach_to(root)
    return root
