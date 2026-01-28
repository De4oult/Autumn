from autumn.cli.environment.commands import environment_group, use_command, install_command, serve_command, doctor_command, lock_command

from rich.console import Console

import click
import sys
import os

class CLI:
    def __init__(self) -> None:
        self.console = Console()

    def info(self, message: str) -> None:
        self.console.print(message)

    def warning(self, message: str) -> None:
        self.console.print(f'[yellow]WARNING[/yellow]: {message}')

    def error(self, message: str) -> None:
        self.console.print(f'[red]ERROR[/red]: {message}')

@click.group(context_settings = { 'help_option_names' : ['-h', '--help'] })
@click.option(
    '--root', 
    type = click.Path(
        file_okay = False,
        dir_okay  = True,
        path_type = str
    ),
    default = '.'
)
@click.pass_context
def autumn(context: click.Context, root: str) -> None:
    context.ensure_object(CLI)

    os.environ['AUTUMN_PROJECT_ROOT'] = os.path.abspath(root)


autumn.add_command(
    environment_group, 
    name = 'env'
)
autumn.add_command(
    use_command, 
    name = 'use'
)
autumn.add_command(
    install_command, 
    name = 'install'
)
autumn.add_command(
    serve_command, 
    name = 'serve'
)
autumn.add_command(
    doctor_command, 
    name = 'doctor'
)
autumn.add_command(
    lock_command, 
    name = 'lock'
)

def main() -> None:
    try:
        autumn.main(prog_name="autumn")
    except Exception as error:
        Console().print(f"[red]ERROR[/red]: {error}")
        sys.exit(1)