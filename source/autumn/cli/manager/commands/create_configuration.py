from autumn.cli.manager.core.templates import render_config_class, ConfigClassTemplateParameters
from autumn.cli.manager.core.naming import normalize_file_name, normalize_class_name
from autumn.cli.manager.core.filesystem import FileSystem
from autumn.cli.console import AutumnConsole, AutumnParameterError

from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import click

@dataclass(frozen=True, slots=True)
class CreateConfigurationCommand:
    file_system: FileSystem
    out: AutumnConsole

    def build(self) -> click.Command:
        @click.command(name = 'create:config')
        @click.argument('configuration_name', type = str)
        @click.option('--yaml', 'yaml_name', type = str, default = None, help = 'Config source filename without extension')
        @click.option('--json', 'json_name', type = str, default = None, help = 'Config source filename without extension')
        @click.option(
            '--project-root',
            type         = click.Path(path_type = Path, exists = False),
            default      = '.',
            show_default = True,
            help         = 'Project root directory',
        )
        def command(
            configuration_name: str, 
            yaml_name: Optional[str], 
            json_name: Optional[str], 
            project_root: Path
        ) -> None:
            if yaml_name and json_name:
                raise AutumnParameterError('Use only one of --yaml or --json (not both).')

            project_root = project_root.resolve()

            archive_config_directory = project_root / 'archive' / 'configuration'
            self.file_system.ensure_dir(archive_config_directory)

            configuration_python_file = project_root / 'core' / 'configuration' / f'{normalize_file_name(configuration_name)}.py'

            decorator = ''
            relative_without_extension = ''

            if yaml_name:
                base = normalize_file_name(yaml_name)

                relative_without_extension = f'archive/configuration/{base}'
                yaml_file = archive_config_directory / f'{base}.yaml'

                created = self.file_system.write_text_if_missing(yaml_file, '')

                if created:
                    self.out.success(f'Created YAML: {yaml_file}')
                
                else:
                    self.out.info(f'YAML exists, skipping: {yaml_file}')

                decorator = f'@yaml(\'{relative_without_extension}\')'

            elif json_name:
                base = normalize_file_name(json_name)

                relative_without_extension = f'archive/configuration/{base}'
                json_file = archive_config_directory / f'{base}.json'

                created = self.file_system.write_text_if_missing(json_file, '{}')

                if created:
                    self.out.success(f'Created JSON: {json_file}')

                else:
                    self.out.info(f'JSON exists, skipping: {json_file}')

                decorator = f'@json(\'{relative_without_extension}\')'

            class_name = normalize_class_name(configuration_name)
            python_text = render_config_class(
                ConfigClassTemplateParameters(
                    class_name                      = class_name,
                    decorator                       = decorator,
                    relative_path_without_extension = (relative_without_extension if relative_without_extension else 'archive/configuration/<source>')                )
            )

            created_python = self.file_system.write_text_if_missing(configuration_python_file, python_text)

            if created_python:
                self.out.success(f'Created config class: {configuration_python_file}')

            else:
                self.out.warning(f'Config class already exists, skipping: {configuration_python_file}')

        return command
