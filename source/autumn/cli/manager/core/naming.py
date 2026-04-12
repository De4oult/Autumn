from autumn.cli.console import AutumnParameterError

import re


WORD_REGEX: re.Pattern = re.compile(r'[A-Za-z0-9]+')


def normalize_file_name(name: str) -> str:
    if not name or not name.strip():
        raise AutumnParameterError('Name must be non-empty')

    string: str = name.strip()

    string = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', string)
    string = re.sub(r'[\s\-\.\/\\]+', '_', string)
    string = re.sub(r'_+', '_', string)

    return string.lower().strip('_')


def normalize_class_name(name: str) -> str:
    if not name or not name.strip():
        raise AutumnParameterError('Name must be non-empty')
    
    temporary_name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)

    parts = WORD_REGEX.findall(temporary_name)
    
    if not parts:
        raise AutumnParameterError('Name must contain alphanumeric characters')

    return ''.join(
        part.capitalize() 
        for part in parts 
    )