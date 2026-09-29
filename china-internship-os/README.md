# China Internship OS

A local, single-user tool for sourcing and tracking a technical internship in China under the
Singapore-China Youth Interns Exchange Scheme (YES). It captures job descriptions you paste,
extracts structured fields with an LLM that you then confirm, and runs deterministic eligibility,
programme-compatibility, tiering and timeline logic over the confirmed data.

The LLM runs through the official Claude Code CLI on your Claude subscription (no API key, no
per-token billing), or through a local Ollama model. The one exception is the optional Jev
decision layer below, which uses a TypeSafe API key kept only on your machine.

Nothing is ever submitted, sent, messaged, emailed or posted by this tool. It generates text for
you to review and send yourself.

## Setup

Requires Python 3.12 or 3.13.

```bash
cd china-internship-os
python3 -m venv .venv              # any Python 3.12 or 3.13; Windows: py -3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ios init
ios llm-check                      # confirms the claude CLI is installed and logged in
```

The default LLM provider is `claude_code`: the tool runs `claude -p` as a subprocess, which uses
the Claude subscription you are logged into (`claude auth login`). If `ios llm-check` cannot find
the CLI, install it with `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux),
`brew install --cask claude-code`, or `npm install -g @anthropic-ai/claude-code`. The subprocess runs
with all tools, hooks, MCP servers and project settings disabled and never persists a session.
If the subscription's usage limit is hit, the command waits and retries until it resets
(`llm.max_wait_minutes` caps the wait). Set `llm.provider: ollama` to use a local model instead.

Models are configured per role in `config/user_facts.yaml`:

```yaml
llm:
  provider: claude_code
  models:
    extraction: sonnet   # extract_job, quality_checklist
    drafting: opus       # messages, bullets, interview prep, YES explanation
```

Run every `ios` command from this directory (it looks for `config/` and `db.sqlite` in the current
directory unless `IOS_ROOT` is set). On Windows, `ios capture --paste` ends input with Ctrl-Z then
Enter on an empty line; on macOS/Linux with Ctrl-D.

`ios init` creates `db.sqlite` in the current directory and, if `config/user_facts.yaml` is absent,
copies `config/user_facts.example.yaml` to it. An existing `user_facts.yaml` is never overwritten.
Edit `config/user_facts.yaml` with your own facts; it is gitignored.

Both invocations work after `pip install -e .`:

```bash
ios init
python -m internship_os init
```

Every command validates the configuration files under `config/` before doing work and exits
non-zero with `file / key / problem` lines if anything is invalid.

## Layout

- `config/` — user facts (personal, gitignored), programme constraints, skill evidence, cities.
- `docs/phase0/` — Phase 0 design documents. Read-only during Phase 1.
- `internship_os/` — the package. `ios` and `python -m internship_os` both run `internship_os.cli:app`.
- `tests/` — pytest suite. Tests use a temporary SQLite database and never call an LLM or the network.
- `packs/` — generated application material per job (gitignored).

## Commands

Every command validates `config/` first and prints one line per state change (object, old, new).

| Command | What it does | Example output (fixtures) |
|---|---|---|
| `ios init` | create tables; copy user_facts from example if absent | `Initialised database: sqlite:///.../db.sqlite` |
| `ios capture --text-file tests/fixtures/jds/hangzhou_ai_app.txt --source shixiseng` | LLM extraction, every field `confirmed: false` | `Captured job 1: AI应用开发实习生 (status DISCOVERED, next: confirm extraction)` |
| `ios capture --paste --source boss` / `--url URL` | paste from stdin, or one GET of a public URL (paste fallback); login wording refuses the page only when its text is under 800 characters or does not read as a JD; the URL is stored normalised (see Lead scan) | same |
| `ios confirm 1` | field-by-field confirmation, company link, eligibility, programme, tiering, quality checklist | `eligibility: LIKELY_ELIGIBLE \| programme: UNKNOWN \| tier: T3` |
| `ios job show 1` / `ios job list [--tier T1] [--status X] [--track AI] [--city 杭州]` | details / sorted table | |
| `ios job fit 1 strong` / `ios job quality 1 strong` | manual ratings, tier rerun | `job 1 quality: unknown -> strong; tier: T2 -> T1` |
| `ios company set 1 --yes-status willing` then `ios recompute` | host status; deterministic recompute, no LLM | `job 1: programme_overall: UNKNOWN -> LIKELY` |
| `ios job status 1 READY_TO_APPLY --next "submit on 实习僧" --due 2026-09-16` | transition; refused into PROGRAMME_CHECK_REQUIRED while any programme dimension is UNKNOWN or INCOMPATIBLE | `job 1 status: SHORTLISTED -> READY_TO_APPLY` |
| `ios job approve-sutd 1` / `ios job dates 1 --start 2027-03-01 --months 5` / `ios job note 1 "..."` | manual programme state (survives recompute) | `DURATION_AND_DATES CONFIRMED` |
| `ios job pack 1` | job.md, fit.md, checklist.md under `packs/` (no LLM) | strengths end with `[EV_...]` |
| `ios job messages 1` / `ios job bullets 1` / `ios job interview-prep 1` | LLM drafts with provenance validation; unsourced claims and invalid bullets are dropped and reported | `Refused unsourced claim: ...` |
| `ios contact add --company 1 --name "..." --role HR --channel wechat` / `list` / `touch 1 --next 2026-09-20` | contacts | |
| `ios llm-check` | CLI presence, version and login state; configured models | `logged in: True \| auth: oauth_token \| provider: firstParty` |
| `ios timeline [--job 1]` / `ios digest` / `ios constraints` | backward-planned dates; daily digest; constraint table and warnings | `CONTRACT MUST BE SIGNED BY 2027-01-10 (123 days). Placeholders in use: Z_VISA_EMBASSY_LEAD_TIME, ENTRY_PERMIT_LEAD_TIME, LOC_LEAD_TIME` |
| `ios ui [--port 8765]` | local web UI on 127.0.0.1: Today, Jobs, Job, Capture, Review, Facts | `Internship OS UI: http://127.0.0.1:8765  (Ctrl-C to stop)` |

## Eligibility reason codes

`ios confirm`, `ios recompute` and the review page run the deterministic eligibility check over the
confirmed fields and store one reason per finding (`ios job show` lists them). Any hard-fail code
makes the job INELIGIBLE; otherwise any review code makes it UNCERTAIN (at best tier T3); soft flags
alone make it LIKELY_ELIGIBLE, and a job with no reason is ELIGIBLE. While a field the check reads
is unconfirmed the result is NOT_RUN, with the reason UNCONFIRMED_FIELDS.

| Effect | Codes |
|---|---|
| INELIGIBLE | DEGREE_INELIGIBLE, GRADUATION_COHORT_INELIGIBLE, EXPLICIT_NATIONALITY_RESTRICTION, EXPLICIT_WORK_AUTHORIZATION_RESTRICTION, EXPLICIT_STUDENT_STATUS_RESTRICTION (postings limited to students of mainland Chinese universities, or to mainland hukou holders or residents), ROLE_CLOSED, DEADLINE_PASSED, FEE_REQUIRED (`pays_fee` confirmed true) |
| UNCERTAIN | RESTRICTION_TEXT_PRESENT_REVIEW, STUDENT_STATUS_REVIEW (a 学信网 check, 国内学籍, a preference for domestic universities), CHINESE_LEVEL_REVIEW, COHORT_TEXT_UNPARSEABLE, USER_COHORT_UNPARSEABLE |
| soft flag | GRADUATION_COHORT_PREFERRED, CHINESE_LEVEL_ABOVE_STATED, DAYS_PER_WEEK_HIGH, EXPERIENCE_YEARS_ASKED, PREFERRED_SKILL_GAPS, REQUIRED_SKILL_GAPS, NOT_ENGINEERING_WORK (`mostly_annotation` or `mostly_sales` confirmed true), UNPAID (`salary_text` contains 无薪, 不提供(实习)工资/薪资/薪酬/补贴, 志愿者 or unpaid), REMOTE_ONLY (`work_mode` confirmed remote), SUMMER_PROGRAMME_TIMING, RESEARCH_ROLE_SIGNALS |

The must-check fields are the inputs of the hard-fail codes (`degree_required`,
`graduation_cohort_text`, `cohort_years`, `cohort_unrestricted`,
`nationality_or_work_auth_restriction`, `role_closed`, `deadline`, `pays_fee`) plus `start_timing`:
`ios confirm`'s `a` still asks each of them and the review page needs their ticks. 中国国籍优先 is a
preference, not a nationality restriction: on its own it gets RESTRICTION_TEXT_PRESENT_REVIEW, not a
hard fail. Jobs flagged UNPAID or REMOTE_ONLY sort last within their tier in `ios job list`, the
Jobs page and the recommendations in `ios digest` and on Today. Confirmed extracted fields feed
these checks; Jev's suggestions never do.

## Personal dates and tracks

The `internship` section of `config/user_facts.yaml` holds the personal dates the programme check
reads and the track order the job lists use (an excerpt, with the example file's values and
`latest_end` set):

```yaml
internship:
  intended_start: 2027-03-01
  latest_end: 2027-08-31        # the internship must end by this date; null = no limit
  track_preference: [AI, AUTO, SWE, other]
```

`latest_end` is optional and must be after `intended_start`. When it is set, DURATION_AND_DATES is
AT_RISK for agreed dates that end after it, and for a posting whose start (or `intended_start`
when the posting names none) plus its minimum duration ends after it. A posting that starts after
`latest_end` is AT_RISK even when it states no minimum, but one that states no duration at all
stays UNKNOWN until you agree dates (`ios job dates`). The end date is the start plus the months,
so a 6-month internship from 1 March ends on 1 September and is AT_RISK against a `latest_end` of
31 August. Programme rules themselves stay in `config/programme_constraints.yaml`.

`AUTO` is the track for automotive roles (vehicles, ADAS, autonomous driving) whose main work is
software or AI (perception, planning, simulation software, vehicle data, tooling); automotive roles
centred on CAD, mechanical, structural, electrical or hardware work are `other`.
`ios job list --track AUTO` and the web filter accept it, and like every track its position in
`track_preference` orders jobs within a tier, after the deadline and host type. Jev never suggests
AUTO, so an AUTO job may show a "Jev suggests" note for another track at review; no gate reads it.

Extracted fields also include `work_mode` (onsite, hybrid, remote or not_stated); a confirmed
`remote`, meaning the whole internship is remote, gives the REMOTE_ONLY flag.

## Web UI

```bash
ios ui                             # then open http://127.0.0.1:8765
```

The web UI is a local, single-user alternative to the terminal for daily use. It listens on
127.0.0.1 only, has no login and no JavaScript, and refuses requests another website could forge
(cross-origin form posts, unknown Host headers). Pages:

- **Today**: the digest (contract deadline, due and upcoming actions, deadlines, recommendations,
  counts, programme warnings) plus captures waiting for review.
- **Capture**: paste a job description and pick its source. The URL box is stored for duplicate
  matching, normalised as described under Lead scan (type it with `https://`: without a scheme its
  query is kept), and is never fetched from the browser; use `ios capture --url` for that.
- **Review**: the browser version of `ios confirm`. Each box shows the extracted value: leave it to
  confirm, change it to override, or empty it to set null. The fields that can make a job ineligible
  need an explicit tick. `ios confirm <id>` still works for the same jobs.
- **Jobs / Job**: the filtered job list, and one job with status changes (through the same
  READY_TO_APPLY programme gate as `ios job status`), next action, notes and contacts.
- **Facts**: timeline, programme constraints with verification dates, and warnings.

Fit, quality, SUTD approval, agreed dates, company settings, recompute and drafting stay in the
terminal; the Job page shows the commands. The Streamlit dashboard (`streamlit run app.py`) was
replaced by `ios ui`; sections 13 and 15 of `docs/WORKFLOW_GUIDE.pdf` still describe it.

## Jev decision layer (optional)

Jev (TypeSafe's System One model) answers a few typed questions about each captured posting: the
role track (AI, SWE, research or other; Jev never suggests AUTO), minimum degree, Chinese level,
start timing, a nationality or visa restriction, fees, data-labelling work and sales work, plus
whether a few extracted values are supported by the text.
Its answers are stored as a `jev_suggestions` job event and shown as notes and warnings on the
review page and before `ios confirm`. They are suggestions only: no eligibility, programme or
tiering rule reads them, and the must-check fields still need your tick.

- Only the pasted posting text and a few values extracted from it are sent. Nothing from
  `user_facts.yaml`, drafts or skill evidence.
- The key stays on your machine: put `TYPESAFE_API_KEY=...` in `.env` (gitignored) or export it.
  It is never written to a tracked file, and a test fails if one ever contains a key.
- `config/decisions.yaml` pins the model and the note thresholds. Set `provider: none` to turn
  Jev off. Without a key, Jev is off and capture works exactly as before.
- `ios llm-check` prints whether Jev is on. Capture prints one line: answers stored, off, or
  unavailable (a Jev failure never stops a capture; one short attempt, no retries).
- To measure Jev before relying on it, label real postings in `data/labelled_postings.jsonl`
  (format: `data/labelled_postings.example.jsonl`; the real file is gitignored) and run
  `.venv/bin/python scripts/eval_prefill.py`. It makes one paid TypeSafe call per labelled
  posting, even with `provider: none`, and measures the posting questions only.

## Lead scan

A scheduled scan outside this tool (实习僧, the YES portal, web search) finds leads and sends you
`ios capture --url <URL> --source shixiseng` commands (`--source yes_portal` for the YES portal,
`--source other` for a web-search lead), which you run yourself. The tool never reads the scan's
board; the command is the whole handoff. Each command is a single GET of that URL (following at
most five redirects), and the captured job then goes through the same confirmation, eligibility,
programme and tiering rules as any other capture.

Login wording on the page (实习僧 headers, YES's "Please log in to apply") refuses it only when the
extracted text is under 800 characters or does not read as a JD, so a full JD that merely links to
login is captured, while a short login page, or one that does not read as a JD, is still refused (a
long 实习僧 login page that mentions 职位 or 招聘 can get through; see `docs/FOLLOW_UPS.md`). When
a page cannot be used the command exits with the reason; paste the text with
`ios capture --paste --source <channel>` instead (the CLI stores no URL for pasted text, so that
job cannot be matched by URL later; the web Capture page keeps its URL box).

Source URLs are stored normalised: scheme and host lower-cased, fragment and trailing slash dropped,
`www.` and the path's case kept, and the query dropped for shixiseng.com, businesschina.org.sg and
their subdomains; other hosts keep it, and the GET itself uses the URL as typed. A lead captured
again through a tracking link such as `…/inn_x?pcm=pc_SearchList` is therefore recognised as a
duplicate of the job already captured from `…/inn_x`, whatever its status.

## Tests

```bash
pytest -q
```

## Environment overrides

- `IOS_ROOT` — project root used to locate `config/` and `db.sqlite` (default: current directory).
- `IOS_DB_URL` — SQLAlchemy URL for the database (default: `sqlite:///<IOS_ROOT>/db.sqlite`).
