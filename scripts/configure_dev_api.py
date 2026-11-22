"""Legacy command: development-key access was removed in phase 3."""

raise SystemExit(
    "Phase 3: use python -m app.bootstrap_auth and POST /api/v1/auth/login. "
    "See docs/api/phase-3.md. No development key is accepted."
)
