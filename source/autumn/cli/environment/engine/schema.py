from __future__ import annotations

from autumn.cli.environment.engine.models import EnvironmentConfig

from pathlib import Path

import json

class SchemaExporter:
    def __init__(self, schema_directory: Path) -> None:
        self.schema_directory = schema_directory

    def export_environment_schema(self) -> Path:
        self.schema_directory.mkdir(parents=True, exist_ok=True)

        schema = EnvironmentConfig.model_json_schema(mode = 'validation')

        out = self.schema_directory / 'environment.schema.json'
        out.write_text(
            json.dumps(
                schema, 
                ensure_ascii = False, 
                indent = 4
            ),
            encoding = 'utf-8'
        )

        return out