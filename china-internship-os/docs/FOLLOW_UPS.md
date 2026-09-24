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

## Recorded during Checkpoint 3

- READY_TO_APPLY gate interpretation: the prompt gates on `programme_overall`, but AT_RISK ranks
  worse than UNKNOWN in the overall ordering, so a job with an AT_RISK duration and an UNKNOWN
  host would have overall AT_RISK and slip through. The gate therefore checks dimensions: any
  UNKNOWN or INCOMPATIBLE dimension refuses the transition; AT_RISK alone proceeds with a
  warning. This matches the architecture document and the definition-of-done for an unknown host.
- `ios recompute` reruns eligibility but does not move a job's pipeline status when a later
  recompute finds INELIGIBLE (for example a deadline that has since passed). The tier becomes
  HOLD and the reason is shown; the terminal-status effect applies at confirmation only.
  Consider applying the terminal effect on recompute too.
- `internship_os/pipeline.py` was added beyond the specified layout to hold the orchestration
  (confirmation finalisation, recompute, transitions) so the CLI and Streamlit page share it.

## Recorded during Checkpoint 5

- Messages are rendered one statement per line with the provenance comment after each line.
  A joined-paragraph rendering (Chinese without line breaks) may read more naturally; the
  provenance comments would then need to sit at the end of the paragraph.
- Recruiter/referral drafts and the YES explanation are two LLM calls. If the YES call fails
  the four recruiter/referral sections are still written and the YES sections say NOT GENERATED.
- `tests/test_safety.py` holds the static safety test instead of a module-specific test file,
  since it spans every module.
- The Streamlit capture form calls the extraction LLM directly; a duplicate shows the candidate
  job and offers a single "create as separate job" button, with attach/cancel left to the CLI.
- Skill matching treats a JD skill as covered when any evidence tag matches by exact,
  token, substring (3+ chars) or difflib ratio 0.85. Chinese-only JD skills rarely match the
  English evidence tags, so REQUIRED_SKILL_GAPS fires often; consider Chinese aliases on tags.

## Recorded after the Phase 1 review

- `nonclaim` statements are now rejected deterministically when they contain a digit, an
  achievement verb, or (in the YES explanation) programme vocabulary. This is a heuristic guard
  on a model-supplied `kind`, not semantic fact-checking; tune the word lists if legitimate
  greetings get refused.
- Mandarin statements are checked after removing the verbatim configured claim, so extra
  proficiency wording appended to the claim is refused.
- The hosted-vendor-prefix check on the old `llm.model` key was dropped when models became
  per-role (`llm.models.*`); with provider ollama the only network call is the POST to
  localhost:11434 whatever the model name.
- Confirmation is committed before the optional quality checklist call so an interrupted
  LLM call cannot discard a confirmed job.

## Recorded when switching to the Claude Code CLI provider

- The `anthropic` API provider and `.env` were removed at the user's request; the tool now runs
  `claude -p` on the user's subscription (or Ollama). The LLM boundary rules are unchanged.
- Models are routed per prompt role (extraction vs drafting) from `user_facts.llm.models`.
- Rate limits: the CLI reports them as `is_error: true` with a message; detection is by keyword
  match, and the wait is unbounded unless `llm.max_wait_minutes` is set. If the CLI's wording
  changes, extend `RATE_LIMIT_PATTERN` in `internship_os/llm.py`.
- `--json-schema` structured output is used when available; text parsing remains as fallback.

## Recorded for the web UI

- The Streamlit page (`app.py`) named in ARCHITECTURE_RECOMMENDATION.md and in the notes above is
  replaced by `ios ui`: FastAPI and Jinja2 pages, no JavaScript, bound to 127.0.0.1.
  `docs/WORKFLOW_GUIDE.pdf` sections 13 and 15 still describe the Streamlit page.
- The browser Review page is the same confirmation as `ios confirm` (`services/review.py`). The
  inputs of eligibility's hard-fail codes need an explicit tick. The web duplicate page offers
  attach, create a separate job, and cancel.
- Not in the web UI yet: fit, quality, SUTD approval, agreed dates, company settings, recompute,
  contact touch and drafting. The Job page shows the commands.
- An always-on launchd agent was deferred: under launchd the `claude` CLI is not on PATH, and a
  long-running server keeps old code loaded while other work changes the same modules.
- Captures run inside the request. With `llm.max_wait_minutes: null` a rate limit keeps the tab
  waiting; submitting twice during extraction makes two LLM calls (the second shows the
  duplicate page).
- The web tests use Starlette's TestClient over httpx, which Starlette now deprecates in favour
  of httpx2.

## Recorded for the Jev decision layer

- Jev runs once after capture (CLI and web) and its answers are stored as a `jev_suggestions`
  job event, not a column, so there was no schema migration. The review page and `ios confirm`
  show them as notes; no gate reads them.
- Four confirmable fields were added: start_timing, pays_fee, mostly_annotation, mostly_sales.
  Stored extractions from before load them as confirmed nulls, so earlier jobs stay confirmed.
  An ASAP start adds "ask HR whether a <intended_start> start works" to the next action at
  confirmation only.
- `ios confirm`'s 'a' now still asks each must-check field (schemas.ALWAYS_CONFIRM_FIELDS).
- The two thresholds in config/decisions.yaml (noul_flag_p 0.7, choice_min_confidence 0.6) are
  starting values. Label 40-60 real postings and run scripts/eval_prefill.py to tune them. The
  script measures the posting questions only; the check__ support questions are not measured.
- Not built: the draft overclaim checker (it would send drafts and evidence to TypeSafe), a
  database column for suggestions, Jev on the Job page after confirmation.
- typesafe-sdk is pinned exactly (0.7.1); the SDK has shipped breaking releases weekly. It pulls
  httpx2 and tenacity alongside the repo's httpx.
- Separate fixes made alongside: EV_MINDEF_DB now refuses Chinese numerals and number words in
  bullets and message statements; "X届及以后" no longer hard-fails later cohorts and "X届优先" is a
  soft flag; summer programmes get the soft SUMMER_PROGRAMME_TIMING flag.
