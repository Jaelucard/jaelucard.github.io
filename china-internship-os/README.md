# China Internship OS

A local, single-user tool for sourcing and tracking a technical internship in China under the
Singapore-China Youth Interns Exchange Scheme (YES). It captures job descriptions you paste,
extracts structured fields with an LLM that you then confirm, and runs deterministic eligibility,
programme-compatibility, tiering and timeline logic over the confirmed data.

Nothing is ever submitted, sent, messaged, emailed or posted by this tool. It generates text for
you to review and send yourself.

## Setup

Requires Python 3.12.

```bash
cd china-internship-os
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # fill in ANTHROPIC_API_KEY or OLLAMA_MODEL
ios init
```

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

## Tests

```bash
pytest -q
```

## Environment overrides

- `IOS_ROOT` — project root used to locate `config/` and `db.sqlite` (default: current directory).
- `IOS_DB_URL` — SQLAlchemy URL for the database (default: `sqlite:///<IOS_ROOT>/db.sqlite`).
