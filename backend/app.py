"""
PrusaSlicer parameter-optimization service.
  - REST API for the web dashboard
  - MCP server (tools) for Claude/agent-driven calibration workflows
  - the optimizer itself: MPC-style receding-horizon parameter search

Run: uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
import json
from typing import Optional

import asyncpg
import numpy as np
from fastapi import FastAPI, HTTPException
from mcp.server.fastmcp import FastMCP
from auth import BearerAuthMiddleware

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="printopt-backend")
mcp = FastMCP("printopt")
pool: Optional[asyncpg.Pool] = None


@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)


@app.on_event("shutdown")
async def shutdown():
    await pool.close()


TARGETS = {
    "flow_tower": {"measurement_type": "width_mm",
                   "target": lambda gp: gp.get("expected_width", 0.4)},
    "temp_tower": {"measurement_type": "stringing_score",
                   "target": lambda gp: 0.0},
}

PARAM_NAME_BY_TEST_TYPE = {
    "flow_tower": "flow_ratio",
    "temp_tower": "nozzle_temperature",
}


def fit_and_recommend(param_values: list[float], measured_values: list[float], target: float) -> dict:
    x, y = np.array(param_values), np.array(measured_values)
    if len(x) < 2:
        raise ValueError("need at least 2 data points to fit")
    a, b = np.polyfit(x, y, 1)
    if a == 0:
        raise ValueError("flat response — can't solve for target with a linear fit")
    recommended = (target - b) / a
    predicted_error = float(np.polyval([a, b], recommended) - target)
    return {
        "recommended_param": float(recommended),
        "model": {"slope": float(a), "intercept": float(b)},
        "predicted_error": predicted_error,
    }


async def run_optimization(printer_id: int, material_id: int, test_run_id: int) -> dict:
    async with pool.acquire() as conn:
        run = await conn.fetchrow("SELECT * FROM test_runs WHERE id = $1", test_run_id)
        if not run:
            raise ValueError(f"test_run {test_run_id} not found")

        results = await conn.fetch(
            "SELECT param_value, measured_value FROM test_results WHERE test_run_id = $1 ORDER BY section_index",
            test_run_id,
        )
        if not results:
            raise ValueError("no measurements recorded for this test run yet")

        cfg = TARGETS.get(run["test_type"])
        if not cfg:
            raise ValueError(f"no target function defined for test_type={run['test_type']}")

        gcode_params = run["gcode_params"]
        gcode_params = json.loads(gcode_params) if isinstance(gcode_params, str) else gcode_params
        target_value = cfg["target"](gcode_params)

        param_values = [float(r["param_value"]) for r in results]
        measured_values = [float(r["measured_value"]) for r in results]
        fit = fit_and_recommend(param_values, measured_values, target_value)

        param_name = PARAM_NAME_BY_TEST_TYPE.get(run["test_type"], run["test_type"] + "_param")
        converged_params = {param_name: fit["recommended_param"]}

        opt_id = await conn.fetchval(
            """INSERT INTO optimization_runs
               (printer_id, material_id, algorithm, input_test_run_ids, converged_params, cost_history)
               VALUES ($1, $2, 'mpc_linear', $3, $4, $5) RETURNING id""",
            printer_id, material_id, [test_run_id],
            json.dumps(converged_params), json.dumps({"fit": fit}),
        )

        await conn.execute(
            "UPDATE parameter_profiles SET active = false WHERE printer_id = $1 AND material_id = $2 AND active",
            printer_id, material_id,
        )
        await conn.execute(
            """INSERT INTO parameter_profiles
               (printer_id, material_id, params, source, optimization_run_id, active)
               VALUES ($1, $2, $3, 'optimized', $4, true)""",
            printer_id, material_id, json.dumps(converged_params), opt_id,
        )

        return {"optimization_run_id": opt_id, **fit, "converged_params": converged_params}


@mcp.tool()
async def create_test_run(printer_id: int, material_id: int, test_type: str, gcode_params: dict) -> dict:
    """Register a new calibration test run (e.g. a Flow Tower about to be sliced/printed)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO test_runs (printer_id, material_id, test_type, gcode_params)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            printer_id, material_id, test_type, json.dumps(gcode_params),
        )
        return {"test_run_id": row["id"]}


@mcp.tool()
async def log_test_result(test_run_id: int, section_index: int, param_value: float,
                           measured_value: float, measurement_type: str, notes: str = "") -> dict:
    """Record one measured data point from a physical calibration print."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO test_results
               (test_run_id, section_index, param_value, measured_value, measurement_type, notes)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            test_run_id, section_index, param_value, measured_value, measurement_type, notes,
        )
        return {"result_id": row["id"]}


@mcp.tool()
async def optimize(printer_id: int, material_id: int, test_run_id: int) -> dict:
    """Run the optimizer against a completed, measured test run and update the active profile."""
    return await run_optimization(printer_id, material_id, test_run_id)


@mcp.tool()
async def get_active_profile(printer_id: int, material_id: int) -> dict:
    """Return the current best-known parameter set for a printer/material pair."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT params, created_at FROM parameter_profiles WHERE printer_id=$1 AND material_id=$2 AND active",
            printer_id, material_id,
        )
        if not row:
            raise ValueError("no active profile yet — run at least one test + optimize()")
        return {"params": json.loads(row["params"]), "as_of": row["created_at"].isoformat()}


@app.get("/api/printers")
async def list_printers():
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch("SELECT * FROM printers ORDER BY name")]


@app.get("/api/materials")
async def list_materials():
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch("SELECT * FROM materials ORDER BY brand, material_type")]


@app.get("/api/test_runs")
async def list_test_runs(printer_id: Optional[int] = None, material_id: Optional[int] = None):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM test_runs
               WHERE ($1::int IS NULL OR printer_id=$1) AND ($2::int IS NULL OR material_id=$2)
               ORDER BY created_at DESC""",
            printer_id, material_id,
        )
        return [dict(r) for r in rows]


@app.get("/api/test_runs/{test_run_id}/results")
async def get_test_results(test_run_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM test_results WHERE test_run_id=$1 ORDER BY section_index", test_run_id
        )
        return [dict(r) for r in rows]


@app.get("/api/profiles/{printer_id}/{material_id}")
async def get_profile(printer_id: int, material_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM parameter_profiles WHERE printer_id=$1 AND material_id=$2 AND active",
            printer_id, material_id,
        )
        if not row:
            raise HTTPException(404, "no active profile")
        return dict(row)


app.mount("/mcp", mcp.sse_app())

# Wrap the complete app so mounted transports, aliases and redirects share the gate.
app = BearerAuthMiddleware(app, os.environ.get("PRINTOPT_API_TOKEN", ""))
