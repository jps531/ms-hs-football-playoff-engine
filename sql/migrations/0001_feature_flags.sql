-- Feature flags (backend/helpers/feature_flags.py): each flag's state, set by the owner on /moderate.
CREATE TABLE IF NOT EXISTS feature_flags (
  name        TEXT        PRIMARY KEY,
  state       TEXT        NOT NULL DEFAULT 'off' CHECK (state IN ('off', 'owner', 'on')),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by  INTEGER     REFERENCES users(id) ON DELETE SET NULL
);
COMMENT ON TABLE feature_flags IS
  'The state of each feature flag declared in backend/helpers/feature_flags.py (a declared flag with no row is off; '
  'a row for a flag no longer declared is ignored). Set on /moderate by the owner.';
COMMENT ON COLUMN feature_flags.state IS
  'off: nobody sees it. owner: only the owner, in a browser signed in to /moderate in the last day. on: everyone.';
COMMENT ON COLUMN feature_flags.updated_by IS 'The user (the owner) who last set it.';
