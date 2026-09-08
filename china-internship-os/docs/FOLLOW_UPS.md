# Follow-ups

Ideas and deviations recorded during Phase 1. Nothing here is implemented in Phase 1.

## Recorded during Checkpoint 1

- `docs/phase0/OPEN_QUESTIONS.md` was not supplied with the Phase 1 prompt. Only
  ARCHITECTURE_RECOMMENDATION.md, ASSUMPTION_LEDGER.md and SPEC_AUDIT.md are in `docs/phase0/`.
  Add the file when available; do not reconstruct it from the ledger's Q-number references.
- The project lives as a subdirectory of the `jaelucard.github.io` repository (the only repository
  available to the session) rather than as its own repository root. Consider moving it to its own
  repository so `.gitignore`, `pip install -e .` and `ios` paths do not depend on the subdirectory.
- `user_facts.internship.min_months` / `max_months` are user preferences supplied by the prompt's
  example file. Programme logic must read durations only from `SUTD_MIN_DURATION` and
  `YES_MAX_DURATION`; consider removing the user-facts duplicates once the programme module exists
  to avoid confusion.
- ARCHITECTURE_RECOMMENDATION.md gives companies a `blacklist_status` column; the Phase 1 prompt
  drops it (blacklist checking is outside the tool per HOST_ONBOARDING_ROUTE). Revisit if SUTD
  provides a way to check companies.
