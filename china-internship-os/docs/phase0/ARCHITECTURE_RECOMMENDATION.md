# ARCHITECTURE_RECOMMENDATION.md
China Internship OS. Prepared 2026-09-07. No code.

## 1. The problem, restated from the objective

You need, in roughly this order of urgency:

1. Answers to five programme questions, because the visa chain and SUTD's own approval run in series before any start date, and your exchange ends in about four months.
2. A fast way to turn a job posting seen anywhere (WeChat screenshot, BOSS page, referral message) into a record you can compare against your eligibility and the programme constraints.
3. A short, honest ranking of which recorded roles to work on today.
4. Evidence-backed application material in Chinese and English that does not overclaim.
5. A tracker that never lets an active application lose its next action.

Everything else in the draft is either a later optimisation (collectors, analytics) or a solution to a problem you will not have at your volume (fingerprint dedup, autofill).

## 2. Recommended V1 architecture

One Python package, one SQLite file, two YAML files, one CLI, one optional Streamlit page.

```
internship_os/
  config/
    user_facts.yaml          # cohort year, graduation date, citizenship, Mandarin level, intended dates, exchange visa type
    programme_constraints.yaml
    skill_evidence.yaml
    cities.yaml              # primary / secondary / expanded lists
  db.sqlite
  internship_os/
    models.py                # SQLAlchemy: Company, Job, JobEvent, Contact
    capture.py               # paste text or URL -> LLM extraction -> confirm -> Job
    eligibility.py           # deterministic
    programme.py             # deterministic, reads constraints YAML
    tiering.py               # deterministic gates + ordinal ratings -> tier
    timeline.py              # backward plan from intended start date
    drafts.py                # LLM: resume tailoring, zh/en messages, YES explanation, interview prep
    digest.py                # counts and today's list
    cli.py
  app.py                     # Streamlit, read-mostly
  packs/<company-role>/      # generated on demand, four files
```

### 2.1 System boundaries

Inside: capture, structured storage, eligibility, programme compatibility, tiering, timeline, drafting, tracking, digest.
Outside, done by you: browsing job sites, deciding, sending messages, submitting applications, emailing SUTD and Business China, reading official pages when a constraint's verification date passes.
Outside, done by nothing: scraping login-walled platforms, autofill, unattended source monitoring.

### 2.2 Deterministic logic versus LLM

| Task | Mechanism | Reason |
|---|---|---|
| Extract fields from a pasted JD (Chinese or English) | LLM, JSON output, every field marked `extracted: true` until confirmed | Unstructured Chinese text with inconsistent formats. |
| Translate and draft messages, tailor resume bullets | LLM with the evidence YAML in context and a hard rule that every bullet cites an evidence id | Language generation. |
| Role quality checklist | LLM proposes ticks for the section-13 signal list; you confirm | Judgement on prose. |
| Candidate eligibility | Deterministic rules over confirmed fields | Must be explainable and testable. |
| Programme compatibility | Deterministic over constraints YAML plus per-company answers | Must never invent a rule. |
| Tiering | Deterministic | Same. |
| Timeline | Deterministic date arithmetic | Same. |
| Dedup | Normalised key match | Same. |

Rule for LLM fields: nothing the eligibility engine reads may be `extracted: true`. The confirm screen exists to flip that flag.

Decide now whether JD text may leave your machine. JD text is public; your resume and documents are not. Recommended default: hosted API for JD extraction and message drafting, local model (your existing Ollama setup) or explicit opt-in for anything that includes your resume.

### 2.3 Data model

Five tables. Everything else is a column, a JSON blob, or a YAML file.

**companies**: id, name_en, name_zh, city, website, host_type (startup / subsidiary / large / MNC / unknown), blacklist_status (unknown / cleared / blacklisted, with checked_at), yes_status (unknown / listed_on_yes / willing / unwilling / confirmed), notes, referral_notes.

**jobs**: id, company_id, title_en, title_zh, city, track (AI / SWE / research / other), source_channel (yes_portal / company_site / boss / shixiseng / niuke / linkedin / wechat / referral / other), source_url, captured_at, deadline, start_date, end_date_or_duration_text, status (pipeline), next_action, next_action_date, eligibility (ELIGIBLE / LIKELY / UNCERTAIN / INELIGIBLE), eligibility_reasons JSON, programme JSON (five dimensions with status and note), fit (strong / ok / weak), quality (strong / ok / weak / unknown), tier (1 / 2 / 3 / hold), referral (none / wanted / have), extracted JSON (raw and confirmed fields: cohort, degree_required, days_per_week, salary_text, required_skills, preferred_skills, language_req, internship_type, description), raw_text, confirmed_at.

**job_events**: id, job_id, at, kind (captured / status_change / applied / message_sent / interview / note / closed), detail. This replaces applications, interviews, and application_events.

**contacts**: id, company_id, name, role, channel, last_contact, next_followup, notes. A job_events row with kind message_sent can reference a contact id in detail.

**user facts** live in YAML, not the DB, because they change rarely and you should be able to read them in one screen.

What was dropped and why:
- job_sources: one job, one source in V1. Add when a second source for the same job actually appears.
- applications: a job has at most one application by you. Status lives on the job.
- referrals, interviews, search_runs, programme_checks: fields, events, or YAML.
- skills, skill_evidence: YAML. Around 20 skills and 30 evidence items do not need SQL.
- programme_constraints: YAML with the spec's record shape, rendered by the dashboard.

Pipeline states: DISCOVERED, PROGRAMME_CHECK_REQUIRED, SHORTLISTED, READY_TO_APPLY, APPLIED, IN_PROCESS (stage text: OA, tech test, interview 1, HR), OFFER; terminal INELIGIBLE, REJECTED, WITHDRAWN, CLOSED. Rule: any non-terminal job must have next_action and next_action_date, enforced on save.

### 2.4 Eligibility engine

Inputs: confirmed extracted fields, user_facts.yaml.
Hard fails: degree_required above bachelor; cohort text excludes your 届; explicit nationality or work-authorisation restriction; deadline passed; role marked closed.
Soft flags (never fail): Chinese-language requirement above your stated level, days_per_week above what the exchange or SUTD allows, years-of-experience asks, preferred skills you lack.
Output: status plus a list of reason codes. Every hard fail cites the field it fired on.

### 2.5 Programme compatibility

Five dimensions, each CONFIRMED / LIKELY / UNKNOWN / AT_RISK / INCOMPATIBLE:

- SUTD_APPROVAL (covers GII approval): per job, defaults UNKNOWN, becomes CONFIRMED when SUTD acknowledges the offer.
- YES_ELIGIBILITY: global. CONFIRMED (user-relayed, 2026-09-07). Kept as a dimension so a written confirmation can be attached and so the record shows why it is confirmed.
- HOST_COMPANY: from companies.blacklist_status (unknown / cleared / blacklisted) and companies.yes_status (unknown / willing / unwilling / confirmed). Blacklisted gives INCOMPATIBLE. Unwilling gives INCOMPATIBLE. Cleared and willing gives LIKELY. Confirmed by SUTD gives CONFIRMED.
- DURATION_AND_DATES: computed. Placement under 4 months (SUTD baseline) or over 6 months (YES cap) gives AT_RISK, since both can be negotiated. Start before the first working day after Chinese New Year 2027 gives AT_RISK. Missing dates gives UNKNOWN.
- IMMIGRATION: global. LIKELY under the agreed plan (return to Singapore for the Z visa). Becomes CONFIRMED when the Z visa is issued. Per job it can still fall to AT_RISK if the host has never processed a foreign intern's entry permit.

Overall programme status is the worst dimension, with INCOMPATIBLE worse than AT_RISK worse than UNKNOWN worse than LIKELY worse than CONFIRMED. A job may only leave PROGRAMME_CHECK_REQUIRED for READY_TO_APPLY when no dimension is UNKNOWN or INCOMPATIBLE. AT_RISK may proceed with a warning.

With the two global gates settled, a freshly captured job's programme status is driven by HOST_COMPANY and dates only. Most jobs will sit at UNKNOWN on HOST_COMPANY until you run the blacklist check (Q8) and, later, ask the employer (Q10).

### 2.6 Ranking: gates plus tiers, no overall number

The draft's nine dimensions collapse as follows.

| Draft dimension | Becomes |
|---|---|
| Candidate Fit, Technical Fit | one ordinal `fit` (strong / ok / weak), set by you after reading the LLM's evidence-matched skill comparison |
| Evidence Strength | a property of each skill in the YAML, shown during fit assessment, not a job score |
| Career Alignment | the `track` field plus your stated preference order (AI, then SWE, then other) |
| Opportunity Quality | ordinal `quality` from the section-13 checklist |
| Programme Confidence | the programme gate above |
| Location Fit | gate from cities.yaml (primary / secondary / expanded / out) |
| Logistics Fit | soft flags from eligibility (days per week, dates) |
| Overall Recommendation | `tier`, computed by rules below |

Tier rules (first match wins):
- HOLD if eligibility is INELIGIBLE, or programme is INCOMPATIBLE, or city is out of scope.
- Tier 1 if eligibility is ELIGIBLE or LIKELY, quality is strong, fit is strong or ok, and programme is not INCOMPATIBLE.
- Tier 2 if eligibility is ELIGIBLE or LIKELY, and (quality is ok with fit strong) or (quality strong with fit weak) or (quality unknown with fit strong).
- Tier 3 otherwise.

Within a tier, sort by deadline, then by host_type preference (startup, then subsidiary of a large company, then large company, then unknown), then by track preference, then by programme status. Host type is a sort key and not a gate, since SUTD stated a preference and not a rule. The cross-track example in the draft (strong backend role versus a research role you do not qualify for) resolves without weights: the research role fails on degree_required and is HOLD.

If after two months of use you find tiers too coarse, add a manual priority field before adding any arithmetic.

### 2.7 Timeline model

Anchor dates from your answers (user facts, to be placed in user_facts.yaml):

| Anchor | Date | Source |
|---|---|---|
| Personal offer deadline | second week of December 2026 (use 2026-12-11) | you |
| Exchange ends | mid-January 2027 (exact date needed) | you |
| Return to Singapore for Z visa | immediately after exchange end | you |
| Intended start | first working week after Chinese New Year 2027 (CNY is 2027-02-06; holiday dates to confirm when the State Council publishes them) | you, calendar |
| Latest end | start + 6 months (YES cap) | verified |
| Earliest acceptable end | start + 4 months (SUTD baseline) | you |

Step chain (verified): contract → LOC (school applies to Business China) → entry permit (host applies at its local work-permit authority) → Z visa (embassy in Singapore) → arrival and medical → work permit within 15 days if ≥ 90 days → residence permit.

Output: for each step, the latest date it must start given a duration, and a single "contract must be signed by" date shown at the top of the dashboard. Durations for LOC and entry permit are placeholders marked UNVERIFIED until Q9 is answered. Working backwards, the current picture is: Z visa needed by about the third week of January 2027 to allow re-entry and a late-February start; entry permit must therefore be issued before you leave Hangzhou; so the contract and LOC must be done well before mid-January. If Q9 says the entry permit takes four weeks in Zhejiang, your real contract deadline is early December, which is why your personal deadline of the second week of December should be treated as a latest date and not a target.

One correction to your understanding: the Z visa is issued by the Chinese Embassy in Singapore on a standard schedule. The step whose duration varies by province is the host's entry permit application, handled by the provincial or municipal work-permit authority. The timeline model puts the provincial variance on that step.

### 2.8 Capture workflow

1. Paste text (or a URL for pages that return content without login; otherwise paste).
2. LLM returns JSON: company, titles, city, cohort, degree, required, preferred, language, days, dates, salary text, internship type, application method.
3. One confirm screen shows the fields with the source sentence beside each. You fix and confirm. Target under 30 seconds.
4. Eligibility, programme, and tier run on save.

Screenshots: V1 accepts an image only if you paste text from it. OCR of Chinese screenshots is V2 and only if screenshots turn out to be a large share of leads.

### 2.9 Application material

Four on-demand files per shortlisted job. Every resume bullet and every message claim must reference a skill_evidence id or be a verbatim user fact. The generator refuses to emit a bullet it cannot tag. The YES explanation is built from the verified host-obligation list and the verified step chain only, with a placeholder sentence for the onboarding route until it is confirmed.

### 2.10 Digest

`python -m internship_os digest` prints: jobs by tier and status, deadlines within 7 days, active jobs with next_action_date today or past, programme dimensions still UNKNOWN, constraints past next_verification_date, days until "offers needed by". No fetching.

## 3. Comparison with the draft

| Area | Draft | Recommendation | Why |
|---|---|---|---|
| Discovery | Collectors for four source classes plus browser capture | Manual paste capture; company-site collectors only for shortlisted companies in V2 | Draft forbids the anti-bot bypass its own collectors would need. |
| Dedup | Fingerprinting, similarity, source merge | Normalised key plus URL | Volume is tens, not thousands. |
| Data model | 12 entities | 4 tables + YAML | Fields not queried do not need tables. |
| Scoring | 9 numbers plus overall | 3 gates, 3 ordinals, rule tiers | Matches the draft's own section 26 intent. |
| Programme rules | Module with validate-programme diffing | YAML with verification dates | Diffing marketing pages is noise. |
| Pipeline | 16 states | 11 | Interview rounds are a stage text. |
| Application pack | 13 files | 4 files | Section 53 wants minimal overhead. |
| Referral | 7-state subsystem | One field plus notes | Same information, no machinery. |
| Timeline | absent | new module | The most decision-relevant computation in the project. |
| User facts | scattered | one YAML | Eligibility needs them in one place. |
| Browser assistance | Phase 4 with autofill | bookmarklet capture only, V2 | Fragile, low payoff. |
| Analytics | Phase 5 | after 30+ outcomes exist | Nothing to learn from earlier. |

## 4. Scope decisions

### WHAT V1 ACTUALLY NEEDS
- user_facts.yaml, programme_constraints.yaml (seeded from ASSUMPTION_LEDGER.md), skill_evidence.yaml, cities.yaml.
- Four tables, migrations optional.
- Capture with LLM extraction and confirm screen.
- Eligibility, programme compatibility, tiering, timeline.
- Drafts: tailored bullets, zh/en recruiter and referral messages, YES explanation, interview prep on demand.
- Digest CLI and a Streamlit page with a programme-status panel, "offers needed by", tiered job list, and active next actions.
- Tests from the draft's section 49 minus those for removed features, plus the two added in SPEC_AUDIT.md.

### WHAT SHOULD WAIT UNTIL V2
- Bookmarklet or extension capture.
- Collectors for company career pages with stable endpoints, shortlisted companies only.
- job_sources table and closure tracking, once a second source per job appears.
- OCR of screenshots.
- Source effectiveness and response analytics.
- Interview question bank per company.

### WHAT SHOULD PROBABLY NEVER BE BUILT
- Scrapers for BOSS直聘, 实习僧, 牛客, 脉脉, LinkedIn.
- Form-field detection and autofill.
- Automatic diffing of official programme pages.
- Any agent that sends messages or submits applications.
- Vector database, embeddings-based matching, learned scoring weights.
- A "question generator" for programme administrators; the questions are already written.

## 5. Human-in-the-loop points

Must stay manual: confirming extracted fields before they feed eligibility; setting fit and quality; changing any constraint with status VERIFIED or USER_CONFIRMED; sending any message; submitting any application; recording an answer from SUTD or Business China.
Automation that saves time without fragility: extraction from paste, drafting, tier recomputation, date arithmetic, digest.
Automation that would create fragility: everything under "never".
