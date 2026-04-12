from dataclasses import dataclass
from rich.console import Console

from click import UsageError

class AutumnParameterError(UsageError):
    ...

@dataclass(frozen = True, slots = True)
class AutumnConsole:
    console: Console

    def success(self, message: str) -> None:
        self.console.print(f'[green]{message}[/green]')

    def info(self, message: str) -> None:
        self.console.print(message)

    def warning(self, message: str) -> None:
        self.console.print(f'[yellow]WARNING[/yellow]: {message}')

    def error(self, message: str) -> None:
        self.console.print(f'[red]ERROR[/red]: {message}')
