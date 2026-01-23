from rich.console import Console

import click

console = Console()

@click.group()
def cli() -> None:
    ...



if __name__ == '__main__':
    cli()