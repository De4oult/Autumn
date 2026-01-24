from __future__ import annotations

from rich.console import Console
from rich.table import Table
from typing import Iterable

from autumn.cli.environment.engine.doctor import DoctorIssue

class UI:
    def __init__(self, console: Console) -> None:
        self.console = console

    def env_list(self, names: list[str], active: str | None) -> None:
        table = Table(title = 'Environments')

        table.add_column('Name', style = 'bold')
        table.add_column('Active')

        for name in names:
            table.add_row(name, '✅' if active == name else '')

        self.console.print(table)

    def doctor(self, issues: Iterable[DoctorIssue]) -> None:
        table = Table(title = 'Doctor')
        table.add_column('Level', style = 'bold')
        table.add_column('Message')

        for issue in issues:
            style = {
                'OK': 'green', 
                'WARNING': 'yellow', 
                'ERROR': 'red'
            }.get(issue.level, 'white')

            table.add_row(f'[{style}]{issue.level}[/{style}]', issue.message)

        self.console.print(table)
