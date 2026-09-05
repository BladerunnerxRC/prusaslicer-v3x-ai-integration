import asyncio
import importlib
import os
import sys
import unittest
import socket
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth import BearerAuthMiddleware

TOKEN = "test-only-token-" + "x" * 32


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, application, path, headers=(), method="GET"):
        messages = []
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": b"", "root_path": "", "headers": list(headers),
                 "server": ("test", 80), "client": ("test", 123)}
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)
        await application(scope, receive, send)
        return messages

    async def test_invalid_credentials_never_reach_any_path(self):
        async def forbidden(*args):
            self.fail("unauthenticated request reached the application")
        app = BearerAuthMiddleware(forbidden, TOKEN)
        invalid = [[], [(b"authorization", b"Bearer wrong")],
                   [(b"authorization", b"Basic " + TOKEN.encode())],
                   [(b"authorization", b"Bearer ")],
                   [(b"authorization", b"Bearer " + TOKEN.encode() + b" ")],
                   [(b"authorization", b"Bearer " + TOKEN.encode())] * 2]
        for path in ["/api/printers", "/mcp", "/mcp/", "/mcp/sse", "/mcp/messages/", "/messages/", "/docs", "/openapi.json", "/unknown"]:
            for method in ["GET", "POST", "OPTIONS", "HEAD"]:
                for headers in invalid:
                    with self.subTest(path=path, method=method, headers=headers):
                        messages = await self.request(app, path, headers, method)
                        self.assertEqual(messages[0]["status"], 401)
                        self.assertIn((b"www-authenticate", b"Bearer"), messages[0]["headers"])

    async def test_valid_token_preserves_stream_and_lifespan(self):
        observed = []
        async def downstream(scope, receive, send):
            observed.append(scope["type"])
            if scope["type"] == "lifespan":
                return
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"event: message\n", "more_body": True})
            await send({"type": "http.response.body", "body": b"data: ok\n\n", "more_body": False})
        app = BearerAuthMiddleware(downstream, TOKEN)
        for path in ["/api/printers", "/mcp/sse", "/mcp/messages/"]:
            messages = await self.request(app, path, [(b"authorization", b"bEaReR " + TOKEN.encode())])
            self.assertTrue(messages[1]["more_body"])
            self.assertEqual(messages[2]["body"], b"data: ok\n\n")
        await app({"type": "lifespan"}, None, None)
        self.assertIn("lifespan", observed)

    def test_configuration_fails_closed(self):
        for token in ["", "short", " " * 32, "x" * 32 + "\n", "é" * 32]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                BearerAuthMiddleware(None, token)

    async def test_actual_application_is_protected_and_keeps_error_semantics(self):
        os.environ["DATABASE_URL"] = "postgresql://unused"
        os.environ["PRINTOPT_API_TOKEN"] = TOKEN
        app = importlib.import_module("app").app
        for path in ["/api/printers", "/mcp/sse", "/mcp/messages/", "/docs"]:
            self.assertEqual((await self.request(app, path))[0]["status"], 401)
        valid = [(b"authorization", b"Bearer " + TOKEN.encode())]
        self.assertEqual((await self.request(app, "/missing", valid))[0]["status"], 404)
        self.assertEqual((await self.request(app, "/api/test_runs/not-an-int/results", valid))[0]["status"], 422)
        self.assertEqual((await self.request(app, "/openapi.json", valid))[0]["status"], 200)

    async def test_live_mcp_and_rest_with_valid_token(self):
        import httpx
        import uvicorn
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        os.environ["DATABASE_URL"] = "postgresql://unused"
        os.environ["PRINTOPT_API_TOKEN"] = TOKEN
        module = importlib.import_module("app")
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def fetch(self, *args): return [{"id": 1, "name": "Printer"}]
            async def fetchrow(self, *args):
                return {"params": '{"flow_ratio": 1.0}', "created_at": datetime.now(timezone.utc)}
        class Pool:
            def acquire(self): return Connection()
        original_pool = module.pool
        module.pool = Pool()
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(module.app, lifespan="off", log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done(): await task
                    await asyncio.sleep(0.01)
                headers = {"Authorization": f"Bearer {TOKEN}"}
                async with httpx.AsyncClient() as client:
                    self.assertEqual((await client.get(base + "/api/printers")).status_code, 401)
                    response = await client.get(base + "/api/printers", headers=headers)
                    self.assertEqual(response.json(), [{"id": 1, "name": "Printer"}])
                    self.assertEqual((await client.post(base + "/mcp/messages/?session_id=unused")).status_code, 401)
                async with sse_client(base + "/mcp/sse", headers=headers) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        self.assertIn("get_active_profile", [tool.name for tool in tools.tools])
                        result = await session.call_tool("get_active_profile", {"printer_id": 1, "material_id": 1})
                        self.assertFalse(result.isError)
                        self.assertEqual(json.loads(result.content[0].text)["params"], {"flow_ratio": 1.0})
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
            sock.close()
            module.pool = original_pool


if __name__ == "__main__":
    unittest.main()
