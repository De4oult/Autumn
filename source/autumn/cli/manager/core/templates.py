from dataclasses import dataclass
from typing import List

import re

@dataclass(frozen = True, slots = True)
class ConfigClassTemplateParameters:
    class_name: str
    decorator: str
    relative_path_without_extension: str

@dataclass(frozen = True, slots = True)
class ControllerTemplateParameters:
    class_name: str
    prefix: str


def render_config_class(parameters: ConfigClassTemplateParameters) -> str:
    lines: List[str] = []

    decorator_line: str = f', {re.match(r'@([a-zA-Z0-9]+)', parameters.decorator)[1]}' if parameters.decorator else ''

    lines.append('from autumn.configuration import Configuration' + decorator_line)
    lines.append('')
    lines.append('')

    if parameters.decorator:
        lines.append(parameters.decorator)
    
    lines.append(f'class {parameters.class_name}(Configuration):')

    lines.append('    ...')
    lines.append('')

    return '\n'.join(lines)


def render_controller(parameters: ControllerTemplateParameters) -> str:
    return (
        'from autumn.rest import Controller, REST\n'
        '\n'
        f'@REST(prefix = \'{parameters.prefix}\')\n'
        f'class {parameters.class_name}(Controller):\n'
        '    def __init__(self) -> None:\n'
        '        ...\n'
    )
