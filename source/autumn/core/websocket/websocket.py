from typing import Dict, Any, Optional, List, Tuple, Callable

class WebSocketDisconnect(Exception):
	def __init__(
        self, 
        code: int = 1000
    ):
		self.code: int = code
		super().__init__(f'WebSocket disconnected with code {code}')

class WebSocket:
    def __init__(
        self, 
        scope: Dict[str, Any], 
        receive: Callable, 
        send: Callable
    ) -> None:
        self.scope: Dict[str, Any] = scope
        self.__receive: Callable = receive
        self.__send: Callable = send

        self.accepted: bool = False
        self.closed: bool = False

    @property
    def path(self) -> str:
        return self.scope.get('path', '')
    
    @property
    def query_string(self) -> bytes:
        return self.scope.get('query_string', b'')
    
    async def accept(
        self,
        subprotocol: Optional[str] = None,
        headers: Optional[List[Tuple[bytes, bytes]]] = None
    ) -> None:
        if self.accepted:
            return
        
        message: Dict[str, Any] = { 'type' : 'websocket.accept' }

        if subprotocol is not None:
            message['subprotocol'] = subprotocol

        if headers is not None:
            message['headers'] = headers

        await self.__send(message)
        self.accepted = True

    async def close(
        self, 
        code: int = 1000, 
        reason: str = ''
    ) -> None:
        if self.closed:
            return
        
        await self.__send({ 
            'type' : 'websocket.close', 
            'code' : code, 
            'reason' : reason 
        })
        self.closed = True

    async def send_text(self, data: str) -> None:
        await self.__send({ 
            'type' : 'websocket.send', 
            'text' :  data
        })

    async def send_bytes(self, data: bytes) -> None:
        await self.__send({ 
            'type'  : 'websocket.send', 
            'bytes' :  data
        })

    async def receive(self) -> Dict[str, Any]:
        return await self.__receive()
    
    async def receive_text(
        self,
        *,
        encoding: str = 'utf-8',
        errors: str = 'strict'    
    ) -> str:
        message = await self.listen()

        if message.get('text') is not None:
            return message.get('text')
    
        if message.get('bytes') is not None:
            return message.get('bytes').decode(encoding, errors = errors)

        raise TypeError('Expected websocket text frame')

    async def receive_bytes(self) -> bytes:
        message = await self.listen()

        if message.get('bytes') is not None:
            return message.get('bytes')
        
        if message.get('text') is not None:
            return message.get('text').encode('utf-8')
        
        raise TypeError('Expected websocket text frame')
    
    async def listen(self) -> Dict[str, Any]:
        while True:
            message = await self.__receive()
            message_type: str = message.get('type')

            match message_type:
                case 'websocket.disconnect':
                    raise WebSocketDisconnect(code = message.get('code', 1000))
                
                case 'websocket.connect':
                    continue

                case 'websocket.receive':
                    return message
                
                case _:
                    continue