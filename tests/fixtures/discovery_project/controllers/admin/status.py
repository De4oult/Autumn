from autumn.controller import REST, get


@REST(prefix = '/nested')
class NestedController:
    @get('/')
    async def index(self) -> dict:
        return {
            'message': 'Nested controller discovered'
        }
