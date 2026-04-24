from autumn.controller import REST, get

from ..services.greeting import GreetingService


@REST(prefix = '/hello')
class HelloController:
    @get('/')
    async def index(self, greetings: GreetingService) -> dict:
        return {
            'message': greetings.message()
        }
