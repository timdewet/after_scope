-- Pre-session experiment declaration: what the user says they're about to image.
-- Files ingested during the session inherit these as fill-only defaults.

ALTER TABLE sessions ADD COLUMN planned_experiment_id INTEGER REFERENCES experiments(id);
ALTER TABLE sessions ADD COLUMN planned_strain TEXT;
ALTER TABLE sessions ADD COLUMN planned_condition TEXT;
ALTER TABLE sessions ADD COLUMN planned_coverslip TEXT;
ALTER TABLE sessions ADD COLUMN planned_notes TEXT;
ALTER TABLE sessions ADD COLUMN planned_dir TEXT;
