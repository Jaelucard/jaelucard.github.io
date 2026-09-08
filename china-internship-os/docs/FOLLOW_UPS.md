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
- The Ollama fallback rejects `user_facts.llm.model` names with hosted-vendor prefixes
  (claude, gpt-, o1/o3/o4, gemini, anthropic/, openai/, google/). Extend the list as needed.
- Confirmation is committed before the optional quality checklist call so an interrupted
  LLM call cannot discard a confirmed job.
