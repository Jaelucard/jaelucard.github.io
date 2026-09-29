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

## Recorded for the lead scan alignment

Changes made so that leads from the scheduled scan (`ios capture --url`) are judged by the scan's
rules, with every point where the work departed from the alignment prompt and why.

- Checkpoint 1: the 实习僧 detail page (`https://www.shixiseng.com/intern/inn_qa5talgymf0o`) could
  not be downloaded from this machine: the host times out at the TCP/TLS handshake for both httpx
  and curl, while `yes.businesschina.org.sg` answers in two seconds. `tests/fixtures/html/
  shixiseng_detail.html`, `test_url_capture_accepts_shixiseng_detail_page` and the font-hidden text
  check wait for a copy saved from the browser (Save Page As, "Webpage, HTML Only", logged out).
- Checkpoint 1: trafilatura drops private-use characters (U+E000 to U+F8FF) during extraction; a
  JD whose digits are such glyphs comes out with the digits missing, not with the glyphs. The
  prompt's check ("3 or more private-use characters in the extracted text") would therefore never
  fire. When the check is added it must count the characters in the raw page text
  (`response.text`) before extraction.
- Checkpoint 1: a login marker now refuses the page only when the extracted text is under
  `LOGIN_WALL_MAX_CHARS` (800) or does not read as a JD. The YES fixture passes
  `looks_like_job_description` with exactly two markers (`intern`, `requirement`), the minimum, so
  a YES posting without "requirement"/"qualification"/"responsibilities" wording would still be
  refused with the login reason. Extend `JD_MARKERS` (for example `per day`, `internship period`)
  if that happens.
- Checkpoint 1: with a login marker present, the JD test is the ordinary
  `looks_like_job_description` (any two `JD_MARKERS` substrings). On 实习僧 the site name contains
  实习 and the navigation contains 职位/招聘, so a login interstitial whose extracted chrome reaches
  800 characters would be forwarded to extraction rather than refused (reviewer's example: 80 x
  "请登录后查看职位详情。招聘"). Nothing behind the wall is fetched and the user still reviews the
  extraction, so the effect is a junk capture, not a scrape. Re-check with the saved 实习僧 page; if
  needed, require a body marker (职责, 任职, 要求, responsibilities, requirement, qualification) when a
  login marker is present.
- Checkpoint 1: committed as "capture: accept full JDs that link to login" instead of the prompt's
  message, because the font-hidden half is not shipped. `tests/fixtures/html/yes_posting.html` is
  the public posting saved verbatim; the repository is public, so the page is published with it (it
  holds no contact details or keys).
- Pushes: the prompt says "Do not push"; the user asked in the chat to push each checkpoint, so
  every checkpoint commit is pushed to `origin` as it lands.
- Checkpoint 2: the posting-dates check adds the JD's `duration_min_months` to the JD start (or to
  `intended_start`), exactly as the prompt says. When the JD states no minimum only the start is
  checked: a start after `latest_end` is AT_RISK, a start in time adds nothing. `add_months(start,
  n)` is the first day after an n-month stint (1 March + 6 months is 1 September), so a stint whose
  last working day is 31 August is AT_RISK against `latest_end` 2027-08-31, as the prompt's own
  example requires. Using the larger of the JD minimum and `SUTD_MIN_DURATION` (read through
  `programme_interval`) would catch more: a JD of 3-6 months with a confirmed start of 2027-05-15 and `latest_end` 2027-08-31
  is LIKELY under the prompt's rule, although the shortest internship the user may do (4 months)
  ends 2027-09-15. The one-line change is `add_months(anchor, max(dmin or lo, lo))`.
- Checkpoint 2: `latest_end` is evaluated only after the earlier returns in `duration_and_dates`
  keep their statuses (a JD start before `intended_start`, a JD with no duration, a duration
  outside the programme interval). The agreed-dates branch checks it after the interval and the
  early-start checks, before CONFIRMED.
- Checkpoint 2: only the programme module reads `latest_end`. Drafts do not show it to the model
  (`drafts._user_facts_json` lists the keys the prompts see), although a statement citing
  `user_facts.internship.latest_end` passes `validate_statements` because the key exists on the
  model, as for every other user_facts key; the timeline anchor ignores it, so the timeline has no
  end bound.
- Checkpoint 2: the config-validation test sits in `tests/test_programme.py` because the prompt
  lists it there; `tests/test_config.py` would be its natural home.
- Checkpoint 3: 全日制在校生 on its own matches none of the student-status lists, as required. If the
  extractor still copies it into `nationality_or_work_auth_restriction`, the pre-existing rule
  applies and the text yields `RESTRICTION_TEXT_PRESENT_REVIEW` (UNCERTAIN), as any unmatched text
  did before; the extraction prompt now says plain full-time-student wording is not a restriction,
  which keeps it out of the field at the source.
- Checkpoint 3: the four student patterns carry `(?<![非不])` / `(?<![不仅])` lookbehinds and the
  hukou pattern a `(?!不限|亦可|均可|皆可|也可)` lookahead, so 非大陆户籍亦可, 大陆户籍不限,
  不限国内高校在读, 不仅限国内高校 and 港澳台及大陆居民均可 no longer hard-fail. The guard is local
  to the match, so inclusive lists such as 大陆居民及外籍均可 or 非中国大陆户籍者亦可 still do, as
  do negations a word earlier such as 不要求大陆户籍 or 不限大陆户籍. The older nationality pattern
  `中国国籍(?!优先)` has the same weakness (非中国国籍亦可, 不要求中国国籍 and 无需中国国籍
  hard-fail) and was left as it was.
- Checkpoint 3: only the exact 中国国籍优先 is exempted from the nationality patterns. 仅限中国籍优先,
  中国大陆籍优先, 中国国籍者优先 and 优先考虑中国国籍 still hard-fail through the older patterns; a
  general "优先 anywhere" rule is a separate decision.
- Checkpoint 3: 仅限大陆高校在读 and 仅限中国大陆高校在读 match a nationality pattern (仅限大陆,
  仅限中国大陆) as well as a student pattern, so they carry two hard codes; 仅限内地高校在读 carries
  only the nationality code because 内地 is not in the student patterns. The outcome is INELIGIBLE
  either way.
- Checkpoint 4: `UNPAID_PATTERN` is the prompt's regex as written. It matches inside longer phrases
  (无薪假期外均有薪资 matches 无薪) and misses 薪资：无; not widened.
- Checkpoint 4: the comment on `jev.CHECKED_FIELDS` ("fields a gate reads that no question above
  covers") drifts: `salary_text`, and `work_mode` from checkpoint 5, now feed eligibility with no
  Jev support check. Jev's questions and `QUESTIONS_VERSION` are unchanged.
- Checkpoint 4: `pays_fee` joins the must-check fields, so `ios confirm`'s 'a' still asks it and the
  review page lists it in the must-check block at the top and needs its tick; nothing else in
  confirmation changed.
