from autumn.cli.autumn import initialize_cli

def main() -> None:
    cli = initialize_cli()
    cli()

if __name__ == '__main__':
    main()