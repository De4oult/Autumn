from __future__ import annotations

from dataclasses import dataclass
from typing import List

from autumn.cli.environment.engine.context import EnvironmentContext


@dataclass
class DoctorIssue:
    level: str 
    message: str


class DoctorService:
    def check(self, context: EnvironmentContext) -> List[DoctorIssue]:
        issues: List[DoctorIssue] = []

        issues.append(DoctorIssue('OK', f'Environment: {context.env_name} ({context.config.type})'))

        env_json = context.paths.environment_json_path(context.env_name)
        issues.append(DoctorIssue('OK' if env_json.exists() else 'ERROR', f'Config file: {env_json}'))

        venv_python = context.venv.python_exe()
        issues.append(DoctorIssue('OK' if venv_python.exists() else 'ERROR', f'Venv python: {venv_python}'))

        if context.dotenv.used_file:
            issues.append(DoctorIssue('OK', f'Dotenv used: {context.dotenv.used_file.name} ({len(context.dotenv.loaded)} vars loaded)'))
        else:
            issues.append(DoctorIssue('WARNING', 'No dotenv file loaded.'))

        for warning in context.dotenv.warnings:
            issues.append(DoctorIssue('WARNING', warning))

        return issues
