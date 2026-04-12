from dataclasses import dataclass
from typing import Protocol

import click


class Command(Protocol):
    def build(self) -> click.Command:
        ...

@dataclass(frozen = True, slots = True)
class CommandRegistry:
    commands: list[Command]

    def attach_to(self, root: click.Group) -> None:
        for command in self.commands:
            root.add_command(command.build())
