import asyncio
import websockets
import json

class WebSocketServer:
    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port
        self.client = None
        self.reconnect_timeout = 3

    async def handle_client(self, websocket, path):
        """Handle client connection.

        Args:
            websocket: WebSocket connection object.
            path: Connection path.
        """
        try:
            if self.client is not None:
                await websocket.close()
                return

            self.client = websocket
            print("Client connected")

            await websocket.send(json.dumps({
                "type": "connection_response",
                "status": "success",
                "message": "Connection successful"
            }))

            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "command_response":
                        await self.process_message(data)
                except json.JSONDecodeError:
                    print("Received invalid JSON message")

        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected, waiting for reconnection...")
            self.client = None

            reconnect_timeout = asyncio.create_task(asyncio.sleep(self.reconnect_timeout))

            while True:
                if self.client is not None:
                    reconnect_timeout.cancel()
                    return

                try:
                    await asyncio.shield(reconnect_timeout)
                    raise ConnectionError("Client reconnection failed")
                except asyncio.CancelledError:
                    return

    async def send_command(self, command):
        """Send command and wait for response.

        Args:
            command: Command to send.

        Returns:
            Response data from client.

        Raises:
            ConnectionError: If no client is connected.
        """
        if self.client is None:
            raise ConnectionError("No client connected")

        command_message = {
            "type": "command",
            "command": command
        }
        await self.client.send(json.dumps(command_message))

        try:
            response = await self.client.recv()
            return json.loads(response)
        except Exception as e:
            print(f"Error waiting for response: {e}")
            raise

    async def process_message(self, data):
        """Process response from client.

        Args:
            data: Response data from client.

        Returns:
            Processed data.
        """
        print(f"Received client response: {data}")
        return data

    def start(self):
        """Start WebSocket server.

        Returns:
            Server instance.
        """
        server = websockets.serve(self.handle_client, self.host, self.port)
        print(f"WebSocket server started at ws://{self.host}:{self.port}")
        return server

async def main():
    """Example usage of WebSocket server."""
    server = WebSocketServer()
    await server.start()

    try:
        while True:
            if server.client:
                try:
                    response = await server.send_command("test_command")
                    print(f"Received command response: {response}")
                except Exception as e:
                    print(f"Command execution failed: {e}")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    asyncio.run(main())
