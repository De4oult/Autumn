from autumn import service


@service
class GreetingService:
    def message(self) -> str:
        return 'Hello from discovery'
