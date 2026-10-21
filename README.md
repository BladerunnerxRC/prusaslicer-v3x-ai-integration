# Work in progress and depends on Prusa v3 gold release


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
cp .env.example .env   # set POSTGRES_PASSWORD
docker compose up --build
```

Dashboard: `https://printopt.shome` (adjust Traefik labels in
`docker-compose.yml` for your own reverse proxy / domain).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and discussion welcome.
This repo doesn't accept direct pushes — fork and open a PR.

## License

MIT — see [LICENSE](LICENSE).
