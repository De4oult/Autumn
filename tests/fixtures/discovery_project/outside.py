from autumn.controller import REST, get


@REST(prefix = '/outside')
class OutsideController:
    @get('/')
    async def index(self) -> dict:
        return {
            'message': 'Must not be discovered'
        }
