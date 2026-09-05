CREATE TABLE printers (
    id                  SERIAL PRIMARY KEY,
    name                TEXT NOT NULL,
    model               TEXT,
    nozzle_diameter_mm  NUMERIC(4,2) DEFAULT 0.40,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE materials (
    id            SERIAL PRIMARY KEY,
    brand         TEXT NOT NULL,
    material_type TEXT NOT NULL,
    color         TEXT,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE test_runs (
    id            SERIAL PRIMARY KEY,
    printer_id    INTEGER NOT NULL REFERENCES printers(id),
    material_id   INTEGER NOT NULL REFERENCES materials(id),
    test_type     TEXT NOT NULL,
    gcode_params  JSONB NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE test_results (
    id                SERIAL PRIMARY KEY,
    test_run_id       INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    section_index     INTEGER NOT NULL,
    param_value       NUMERIC NOT NULL,
    measured_value    NUMERIC,
    measurement_type  TEXT NOT NULL,
    image_url         TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE optimization_runs (
    id                  SERIAL PRIMARY KEY,
    printer_id          INTEGER NOT NULL REFERENCES printers(id),
    material_id         INTEGER NOT NULL REFERENCES materials(id),
    algorithm           TEXT NOT NULL DEFAULT 'mpc_linear',
    input_test_run_ids  INTEGER[] NOT NULL,
    converged_params    JSONB NOT NULL,
    cost_history        JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE parameter_profiles (
    id                    SERIAL PRIMARY KEY,
    printer_id            INTEGER NOT NULL REFERENCES printers(id),
    material_id           INTEGER NOT NULL REFERENCES materials(id),
    params                JSONB NOT NULL,
    source                TEXT NOT NULL DEFAULT 'optimized',
    optimization_run_id   INTEGER REFERENCES optimization_runs(id),
    active                BOOLEAN NOT NULL DEFAULT true,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_one_active_profile
    ON parameter_profiles(printer_id, material_id) WHERE active;

CREATE INDEX idx_test_runs_printer_material ON test_runs(printer_id, material_id);
CREATE INDEX idx_test_results_run ON test_results(test_run_id);
