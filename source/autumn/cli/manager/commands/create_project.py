from autumn.cli.manager.core.filesystem import FileSystem
from autumn.cli.console import AutumnConsole

from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen = True, slots = True)
class CreateProjectCommand:
    file_system: FileSystem
    out: AutumnConsole

    def build(self) -> click.Command:
        @click.command(name = 'create')
        @click.argument('project_name', type = str)
        def command(project_name: str) -> None:
            root = Path(project_name).resolve()

            directories = [
                root / 'core' / 'configuration',
                root / 'core' / 'controllers',
                root / 'core' / 'services',
                root / 'core' / 'data' / 'schemas',
                root / 'content',
                root / 'archive' / 'configuration',
                root / 'archive' / 'log'
            ]

            for directory in directories:
                self.file_system.ensure_dir(directory)

            self.out.success(f'Project created: {root}')

        return command
