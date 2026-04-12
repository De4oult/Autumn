from dataclasses import dataclass
from pathlib import Path

import click

from autumn.cli.manager.core.templates import render_controller, ControllerTemplateParameters
from autumn.cli.manager.core.naming import normalize_file_name, normalize_class_name
from autumn.cli.manager.core.filesystem import FileSystem
from autumn.cli.console import AutumnConsole


def ensure_controller_suffix(class_name: str) -> str:
    return class_name if class_name.endswith('Controller') else f'{class_name}Controller'


@dataclass(frozen = True, slots = True)
class CreateControllerCommand:
    file_system: FileSystem
    out: AutumnConsole

    def build(self) -> click.Command:
        @click.command(name = 'create:controller')
        @click.argument('name', type = str)
        @click.option('--prefix', type = str, default = '/', show_default = True)
        @click.option(
            '--project-root',
            type         = click.Path(path_type = Path, exists=False),
            default      = '.',
            show_default = True,
            help         = 'Project root directory (where core/ is)',
        )
        def command(name: str, prefix: str, project_root: Path) -> None:
            project_root = project_root.resolve()

            controllers_dir = project_root / 'core' / 'controllers'
            self.file_system.ensure_dir(controllers_dir)

            raw_class = normalize_class_name(name)
            class_name = ensure_controller_suffix(raw_class)

            file_base = normalize_file_name(class_name)
            file_path = controllers_dir / f'{file_base}.py'

            text = render_controller(
                ControllerTemplateParameters(
                    class_name = class_name,
                    prefix = (prefix or '/'),
                )
            )

            created = self.file_system.write_text_if_missing(file_path, text)

            if created:
                self.out.success(f'Created controller: {file_path}')

            else:
                self.out.warning(f'Controller already exists, skipping: {file_path}')

        return command
