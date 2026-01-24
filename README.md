# Autumn

## Feauters
[+] Class Based @REST
[+] ASGI
[+] startup/shutdown hooks
[+] middlewares
[+] @query, @body
[+] Pydantic validation
[+] @json_response
[+] Auto injection 

[] Cors
[] Static
[] Resources

[] Class based returns
- Private, Casted types
- to json

[+] OpenApi
- [+] Builder
- [+] Viewer
[] Docstring Parser
[] curl export/auto Postman

[] config collector

[] repo by names
[] ORM/Models

[] Database/Cache/Logging/Queue providers

[] Auth
[] WebSocket signaling

[] cli
- environment management
- serve
- service:create
- controller:create
- config:create
- repository:create

[] testing

[] Rework exceptions screen
- 1xx - 
- 2xx - sunny autumn
- 3xx - 
- 4xx - yellow autumn/fog
- 5xx - rain

# Project
| app/
| | services/
| | controllers/
| | | schemas/
| | repositories/
| | | models/
| | | | user.py
| | | users.py
| database
| | migrations
| | seeders
| static
| | resources
| | templates
| logs/
| app.py

# Example
```python
from autumn import Autumn, REST, get, post, Request, JSONResponse, query, body, json_response, HTMLResponse, dependency, service

from pydantic import BaseModel, Field
from typing import Optional

app = Autumn()

class DBClient:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def get_dsn(self) -> str:
        return self.dsn

@dependency
async def db() -> DBClient:
    return DBClient(dsn = 'https://google.com')

@service
class UserService:
    def __init__(self, db: DBClient):
        self.db = db

    def get_db_dsn(self) -> str:
        return self.db.get_dsn()
        

class UserSchema(BaseModel):
    name: str = Field(..., min_length=4, max_length=10)
    age: int = Field(..., ge=13, le=150)
    is_male: Optional[bool] = True


@app.startup
async def connect_to_db():
    print('Connecting Database')


@app.shutdown
async def disconnect_to_db():
    print('Disconnecting Database')


@app.middleware.before
async def log_request(request, call_next):
    print(">> Request received:", request.method, request.path)
    return await call_next(request)


@app.middleware.before(path='/users/current/{name:str}', method='GET')
async def test(request, call_next):
    print("TEST")
    return await call_next(request)


@app.middleware.after(path='/users/test', method='POST')
async def log_response(request, call_next):
    response = await call_next(request)
    print("<< Response sent:", response.status)
    return response


@REST(prefix='/users')
class UserController:
    def __init__(self, users: UserService):
        self.users = users

    @get('/{id:int}')
    @post('/{id:int}')
    async def get_users(self, request: Request, id: str):
        return JSONResponse({'id': self.users.get_db_dsn()})

    @get('/')
    @query.integer('page', default=10)
    async def search(self, request: Request):
        page = request.query.page

        return JSONResponse({'page': page})

    @post('/test')
    @body(UserSchema)
    async def create_user(self, request: Request, body: UserSchema):
        return JSONResponse({'ok': True, 'user': body.model_dump(mode='json')})

    @get('/current/{name:str}')
    async def current_name(self, request: Request, name: str):
        return HTMLResponse(name)

    @get('/test_json_response/{name:str}')
    @json_response
    async def get_test_user(self, request: Request, name: str):
        return UserSchema(name=name, age=15)

```