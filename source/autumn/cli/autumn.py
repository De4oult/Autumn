# from autumn.cli.environment.commands import

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

context = click.make_pass_decorator(CLI, ensure = True)

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
@context
def autumn(app: CLI, root: str) -> None:
    os.environ['AUTUMN_PROJECT_ROOT'] = os.path.abspath(root)


def main() -> None:
    try:
        autumn(prog_name = 'autumn')

    except Exception as error:
        Console().print(f'[red]ERROR[/red]: {error}')
        sys.exit(1)