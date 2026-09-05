# PrusaSlicer v3.x AI Integration

AI-driven parameter optimization for PrusaSlicer 3.0 calibration prints
(Flow Tower, Temp Tower, etc.) — an MCP server + optimizer, a Postgres
database, and a web dashboard, running in Docker.

## Status

Early/experimental. PrusaSlicer 3.0 itself is in public preview as of
September 2026 — the Lua plugin API is explicitly unstable and undocumented
by Prusa at this point. This project treats the bundled Flow Tower / Temp
Tower Lua plugins as the API reference until official docs exist.

## Architecture

- **backend/** — FastAPI service exposing both a REST API (for the
  dashboard) and an MCP server (for Claude/agent-driven calibration
  workflows). Contains the optimizer: a receding-horizon parameter search
  fit against measured test data.
- **db/** — Postgres schema: printers, materials, test runs, measurements,
  optimization runs, active parameter profiles.
- **web/** — Static dashboard for reviewing test history and current
  optimized parameters.

## Quick start

```bash
cp .env.example .env   # set POSTGRES_PASSWORD and PRINTOPT_API_TOKEN
docker compose up --build
```

Dashboard: `https://printopt.shome` (adjust Traefik labels in
`docker-compose.yml` for your own reverse proxy / domain).

The backend requires `PRINTOPT_API_TOKEN`: generate a random token with
`python -c "import secrets; print(secrets.token_urlsafe(32))"` and put it in `.env`.
Startup fails if it is missing, shorter than 32 ASCII characters, or contains whitespace.
Direct uvicorn startup also requires this environment variable alongside `DATABASE_URL`.

Enter the token in the dashboard and click **Connect**. It stays in page memory
until reload; it is not saved in browser storage or sent in URLs. Configure MCP
clients to send `Authorization: Bearer <token>` on **both** the SSE connection and
message POST requests. All backend HTTP paths, including documentation and redirects,
require the token. Use HTTPS through the reverse proxy; do not expose plain HTTP
backend traffic to untrusted networks.

This single-operator deployment uses one shared credential granting access to all
calibration tools and reads. It does not implement per-user or per-printer permissions.
Rotate the token by updating `.env` and recreating the backend; reconnect clients afterward.
The allowlist file remains an unenforced placeholder and is not an authentication control.

MCP clients connect to `https://mcp.printopt.shome/mcp/sse`. The SDK is pinned to
1.9.0 to support `sse_app()` and mounted SSE message URLs; the former 1.2.0 pin
did not provide `sse_app()`. The SDK reads the ASGI mount prefix so message POST
URLs stay under `/mcp`.

Run backend regression tests after installing `backend/requirements.txt`:
`python -m unittest discover -s backend/tests -v`. Tests exercise authentication,
authorized REST, and a real local MCP session with a fake database (no Postgres required).
For the dashboard test, run `npm install` and `npx playwright install chromium` in
`web/`, then `npm test`. Alternatively set `BROWSER_CHANNEL=msedge` to use installed Edge.

## Contributing

Dashboard regression test (Node.js required):

```bash
cd web
npm install
npx playwright install chromium
npm test
```

To use an installed Edge browser instead, set `BROWSER_CHANNEL=msedge`.

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and discussion welcome.
This repo doesn't accept direct pushes — fork and open a PR.

## License

MIT — see [LICENSE](LICENSE).
