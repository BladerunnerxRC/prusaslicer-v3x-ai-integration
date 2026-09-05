"""Shared-token authentication at the outer HTTP boundary, including MCP."""

import hmac

from starlette.responses import JSONResponse


class BearerAuthMiddleware:
    def __init__(self, app, token: str):
        if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError("PRINTOPT_API_TOKEN must contain at least 32 ASCII characters without whitespace")
        self.app = app
        self.token = token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # No WebSocket interface is currently supported.
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = [value for name, value in scope["headers"] if name.lower() == b"authorization"]
        authorized = False
        if len(headers) == 1:
            scheme, separator, credential = headers[0].partition(b" ")
            authorized = (
                scheme.lower() == b"bearer"
                and bool(separator)
                and hmac.compare_digest(credential, self.token)
            )
        if not authorized:
            response = JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
