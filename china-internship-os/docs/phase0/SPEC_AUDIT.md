# SPEC_AUDIT.md
China Internship OS, Draft Specification v0.1
Phase 0 audit. Prepared 2026-09-07. No code produced.

## How to read this

Each material requirement gets one verdict: KEEP, MODIFY, DEFER, REMOVE, VERIFY_FIRST. Each also gets a type: PRODUCT, PROGRAMME, TECHNICAL, IMPL_CHOICE, USER_PREF, UNVERIFIED_ASSUMPTION. Anything other than KEEP has a reason.

Two facts found during the audit change the shape of the whole project and are referenced throughout. They are documented fully in ASSUMPTION_LEDGER.md.

F1. YES caps an internship at six months (verified, YES portal, 2026-09-07). Your originally stated GII structure was an eight-month internship. Resolved 2026-09-07: the placement is at most six months, SUTD baseline is four months, intended start after Chinese New Year 2027.

F2. YES eligibility excludes anyone who "participated in the Scheme previously" (verified, YES FAQ). Resolved 2026-09-07: SUTD and Business China confirmed the Oct–Dec 2025 MolarData internship was a ZJU-hosted programme element, not YES. YES is open to you.

Both resolutions are user-relayed. The audit text below is kept as written so the reasoning is visible; ASSUMPTION_LEDGER.md carries the current statuses.

## Sections 1–3. Operating principle, review mandate, source hierarchy

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Four categories (verified fact, user fact, inference, implementation choice) | PRODUCT | KEEP | Correct, and the audit found cases where it matters (F1, F2). |
| Specification audit with per-assumption fields | PRODUCT | KEEP | Done in ASSUMPTION_LEDGER.md. |
| Source hierarchy items 1–11 | PROGRAMME | MODIFY | Item 5 ("current SUTD public GII documentation") does not exist as far as a public search on 2026-09-07 can find. SUTD's public pages cover GEXP and DGIT, not a programme named GII. Rank 5 collapses into rank 1/2 (cohort instructions and CDC emails). Also add the YES portal's own process page above the YES FAQ, because the FAQ contains stale text (see F5 in the ledger). |
| "Prefer most specific and recent instruction for my cohort" | PROGRAMME | KEEP | |

## Section 4. Programme compliance subsystem

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Dedicated module, machine-readable constraints, human-readable validation doc | TECHNICAL | KEEP | |
| Constraint record fields (constraint_id, statement, status, source, ...) | TECHNICAL | MODIFY | Keep the fields. Drop the requirement that this be a module with code. In V1 it is one YAML file and one rendered page. There is no logic to write beyond "load YAML, show it, warn if next_verification_date passed". |
| Example YES_MAX_INTERNSHIP_DURATION = 6 months, VERIFIED | PROGRAMME | KEEP | Verified. It is also the single most consequential constraint in the project because of F1. |
| Do not hard-code rules elsewhere | TECHNICAL | KEEP | |

## Sections 5–7. Programme questions, self-sourced validation, immigration

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Validate the GII/YES relationship list | PROGRAMME | VERIFY_FIRST | Partially done. Verified: YES eligibility, 6-month cap, LOC process, host obligations. Not verifiable publicly: any GII-specific rule. See ledger and OPEN_QUESTIONS.md. |
| Self-sourced employer workflow | PROGRAMME | VERIFY_FIRST | Public YES material says students may use YES-listed roles "or tap on the current internship programmes arranged by their respective schools", and that the school applies for the LOC. It says nothing about a student-sourced company. Two plausible routes exist (company registers on the YES portal; SUTD submits it as a school-arranged placement). Which one applies to you is Q3 in OPEN_QUESTIONS.md. Do not encode either. |
| Immigration transition list | PROGRAMME | VERIFY_FIRST | Verified: the YES sequence assumes the intern applies for the Z visa at the Chinese Embassy in Singapore, then applies for the work permit within 15 days of arrival for stints of 90 days or more, then a residence permit. Verified: China's National Immigration Administration lists Z-visa entry as the standard basis for a work residence permit; entrants on other visa types must meet high-level talent or similar criteria. In-country conversion exceptions exist and are at local PSB discretion. Whether any of that applies to a student finishing a ZJU exchange is unknown. Keep the prominent PROGRAMME CRITICAL flag. |
| "Do not make immigration advice based on inference" | PROGRAMME | KEEP | |
| System continues developing while unresolved, but may not declare PROGRAMME_COMPATIBLE | PRODUCT | KEEP | |

## Section 8. Programme compatibility gate

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Separate candidate eligibility from programme compatibility | PRODUCT | KEEP | This is the best idea in the spec. |
| Seven compatibility dimensions | TECHNICAL | MODIFY | Reduce to five. SUTD_APPROVAL and GII_COMPATIBILITY are the same question for you (SUTD is the only body that approves a GII placement). DATE_COMPATIBILITY and DURATION_COMPATIBILITY are one dimension driven by one constraint record (allowed start, allowed end, max 6 months under YES). Keep YES_COMPATIBILITY (is the scheme open to you and to this host), HOST_COMPANY_COMPATIBILITY, IMMIGRATION_COMPATIBILITY. |
| Statuses CONFIRMED / LIKELY / UNKNOWN / AT_RISK / INCOMPATIBLE | TECHNICAL | KEEP | |
| PROGRAMME_CHECK_REQUIRED instead of rejection | PRODUCT | KEEP | |

## Sections 9–14. Profile, two tracks, quality, research roles

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Profile built from evidence, not assumed skill list | PRODUCT | KEEP | |
| Track A / Track B with Chinese and English title lists | PRODUCT | KEEP | The Chinese terms are usable as-is. |
| "Do not treat Track B as inferior" | USER_PREF | KEEP | |
| Three separate scores (fit, alignment, quality) | TECHNICAL | MODIFY | See section 25. Keep the separation, drop the numbers. |
| Role quality signals list | PRODUCT | KEEP | Implement as an LLM-assisted checklist the user confirms, not as a computed score. |
| Research-role gating (Master's, PhD, publications, CUDA) | PRODUCT | KEEP | Deterministic hard-fail on "硕士及以上" / "博士" in the required-degree field, soft flag on the rest. |

## Section 15. Geography

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Hangzhou/Shanghai primary, Suzhou/Nanjing secondary, expandable | USER_PREF | KEEP | The YES portal already lists Hangzhou, Shanghai, Suzhou, Nanjing, Wuxi and Taizhou as filter cities, so the region is not exotic for the scheme. |
| Configurable city list | TECHNICAL | KEEP | One list in config. |

## Section 16. Internship types

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Parse 日常实习 / 暑期实习 / 校招 / 转正 / 留学生实习 etc. | PRODUCT | KEEP | Parsed by the extraction step, stored as an enum plus free text. |
| Graduation cohort parsing (2027届, 2028届) | PRODUCT | KEEP | This is a hard eligibility field. Note your own cohort must be stated by you and stored as a user fact; it is not in the spec. |

## Sections 17–19. Sources, anti-bot, manual capture

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Four source classes | PRODUCT | KEEP as taxonomy | |
| Class A collectors (YES portal, company career pages) | TECHNICAL | DEFER to V2 | The YES portal requires login to apply and is a small curated list. Browsing it by hand weekly costs less than maintaining a collector. Company career pages vary; build collectors only for companies that appear on the shortlist and have a stable JSON endpoint. |
| Class B collectors (实习僧, BOSS直聘, 牛客, 脉脉) | TECHNICAL | REMOVE as automated collectors | All four have login walls, anti-bot controls, and terms that prohibit scraping. The spec already says not to bypass any of that. What remains is manual capture, which section 19 covers. Listing them as "collectors" invites building something the spec forbids. |
| Class C (LinkedIn, MNC career sites) | TECHNICAL | DEFER | Same reasoning. Manual capture in V1. |
| Class D (social, WeChat, alumni) | PRODUCT | KEEP as manual capture input | |
| Browser-assisted capture ("Capture Job" from an open tab) | TECHNICAL | DEFER to V2 | A bookmarklet or extension that posts the page's visible text to a local endpoint is the right shape. It is not needed for V1 because paste-text import gives the same result with one extra keystroke. |
| Paste-text import | PRODUCT | KEEP | This is the V1 ingestion path. |
| Under-30-second manual capture target | PRODUCT | KEEP | Achievable with paste → LLM extraction → one confirm screen. |

## Sections 20–22. Data model, job fields, deduplication

| Item | Type | Verdict | Reason |
|---|---|---|---|
| SQLite V1, Postgres-migratable | IMPL_CHOICE | KEEP | |
| Twelve entities | TECHNICAL | MODIFY | V1 needs five: companies, jobs, job_events, contacts, and a settings/user-facts record. Reasoning per entity is in ARCHITECTURE_RECOMMENDATION.md. |
| Job field list (about 35 fields) | TECHNICAL | MODIFY | Split into columns you query on (company, role, city, source_url, status, next_action_date, deadline, eligibility, programme status, tier) and a JSON `extracted` blob for everything else (requirements, salary text, days per week, cohort text). Promote a field to a column only when a query needs it. |
| Deduplication with fingerprinting and JD similarity | TECHNICAL | DEFER to V2 | With manual capture at your volume (tens of jobs per month, not thousands), a normalised (company, role, city) key plus URL match catches nearly everything, and you will notice the rest. Fingerprinting is a solution to a problem automated collection would create. |
| Preserve conflicting source values | PRODUCT | DEFER with dedup | |

## Sections 23–24. Eligibility engine

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Runs before ranking; four outcomes | PRODUCT | KEEP | |
| Hard-fail codes | PRODUCT | KEEP | Add ALREADY_PARTICIPATED_IN_YES as a programme-level (not job-level) hard fail pending Q2. |
| Chinese-language requirement as soft flag | PRODUCT | KEEP | |
| REQUIRED vs PREFERRED distinction | PRODUCT | KEEP | Extraction must capture the two as separate lists. |

## Sections 25–26. Scoring

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Nine numeric dimensions plus overall recommendation | TECHNICAL | MODIFY | Three of the nine are gates, not scores (Programme Confidence, Location Fit, Logistics Fit). Two overlap almost entirely (Candidate Fit and Technical Fit; Evidence Strength is a property of the profile, not the job). An overall number invites the exact failure the spec warns about, because any weight set that makes a strong SWE role beat a weak AI role can be gamed by title keywords. Replace with gates plus three ordinal ratings and a rule-based tier. Details in ARCHITECTURE_RECOMMENDATION.md. |
| Explain every material score | PRODUCT | KEEP | Easier with ordinal ratings, since each has a one-line justification. |
| Cross-track comparison example | PRODUCT | KEEP as a test case | |

## Sections 27–28. Skill evidence

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Skill → evidence → source graph | TECHNICAL | MODIFY | It is a graph in the abstract. Store it as one hand-maintained YAML file. Query it with a loop. Never fabricate evidence stays as a hard rule enforced by requiring an evidence id on every tailored bullet. |
| Skill transfer analysis | PRODUCT | KEEP | Achieved by letting one evidence item carry multiple skill tags. |

## Sections 29–30. Referral, contacts

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Seven referral states, per-company referral policy research | TECHNICAL | MODIFY | Collapse to one field on the job (referral: none / wanted / have) and one note field. Per-company policy research is manual and belongs in the company notes. Query templates (公司 + 日常实习 + 内推) are a static text list, not a feature. |
| Contacts entity | PRODUCT | KEEP, minimal | name, company, role, channel, last_contact, next_followup, notes. |
| No automatic messaging | PRODUCT | KEEP | |

## Sections 31–34. Application pack, resume rules, Chinese material, YES explanation

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Thirteen-file application pack | TECHNICAL | MODIFY | Reduce to four on-demand files: job.md (captured JD and source), fit.md (eligibility, programme status, evidence-backed strengths, gaps), messages.md (zh and en recruiter and referral messages), checklist.md. Interview-prep is generated when an interview is scheduled, not at shortlist. Thirteen files per role is administrative overhead the spec elsewhere says it wants to minimise. |
| Resume tailoring = selection, emphasis, reordering, no invention | PRODUCT | KEEP | |
| Chinese and English resumes and messages | PRODUCT | KEEP | |
| Do not exaggerate Mandarin level | PRODUCT | KEEP | Your stated language fact is "speaks Chinese"; the level must be stated by you before any message claims one. |
| YES employer explanation pack from verified information | PRODUCT | VERIFY_FIRST | Can be drafted now from verified host obligations (stipend, supervisor, feedback to Business China, LOC and entry-permit steps). Must not state how a self-sourced company gets onto the scheme until Q3 is answered. |

## Sections 35–37. Pipeline, human approval, daily scan

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Sixteen pipeline states | TECHNICAL | MODIFY | Collapse OA, TECHNICAL_TEST, INTERVIEW_1, INTERVIEW_2, HR_INTERVIEW into one state IN_PROCESS with a free-text stage. REVIEW and SHORTLISTED are one decision. REFERRAL_SEARCH is a flag, not a state. Result is nine states plus terminal. |
| next_action and next_action_date mandatory on active items | PRODUCT | KEEP | |
| No auto-submit, no auto-send | PRODUCT | KEEP | |
| Form-field identification and autofill | TECHNICAL | REMOVE | Autofill on Chinese platforms with anti-bot controls is fragile and yields minutes of savings per application at most. Not worth the maintenance. |
| Daily scan command that fetches public sources | TECHNICAL | DEFER to V2 | In V1 "scan" is "recompute eligibility, tiers, and the digest from what is in the database". |
| Digest counts | PRODUCT | KEEP | |

## Sections 38–41. Search matrix, watchlist, source effectiveness, freshness

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Auto-generated query matrix | TECHNICAL | MODIFY | Generate the query strings as a printable list you paste into 实习僧 / BOSS by hand. No execution layer. |
| Company watchlist | PRODUCT | VERIFY_FIRST | Your memory of the programme says "internship at a Chinese startup". If GII restricts host type, Alibaba, ByteDance, Ant, NetEase and Hikvision may be out of scope. Q6 in OPEN_QUESTIONS.md. Keep the list, tag each company with host_type until answered. |
| Source effectiveness analytics | TECHNICAL | DEFER to V2 | Needs dozens of outcomes to mean anything. |
| first_seen / last_seen / POSSIBLY_CLOSED | TECHNICAL | DEFER with collectors | With manual capture, closure is something you observe and record. |
| Never delete history | PRODUCT | KEEP | |

## Sections 42–45. Dashboard, non-blocking, question generator, rule refresh

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Programme status panel | PRODUCT | KEEP | Rendered straight from the constraints YAML. |
| Do not block on uncertainty | PRODUCT | KEEP | |
| Question generator | PRODUCT | MODIFY | The questions are known now (OPEN_QUESTIONS.md). A generator implies new questions will be discovered by the system; they will be discovered by you. Store the question, recipient, date sent, and answer on the constraint record. |
| validate-programme command that diffs official sources | TECHNICAL | REMOVE | Diffing WordPress pages for rule changes is brittle and would produce noise every time the YES site changes a banner. Replace with next_verification_date per constraint and a warning when it passes. You re-read the page. |

## Sections 46–47. Privacy, stack

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Local-only, .env, .gitignore, no identity documents in Git | TECHNICAL | KEEP | |
| Python 3.12, SQLite, SQLAlchemy, Pydantic, Streamlit | IMPL_CHOICE | KEEP with one note | Streamlit is fine for read-only dashboards and simple forms. If the confirm-extraction screen becomes annoying in Streamlit, a CLI with rich tables is an acceptable fallback. Do not add a JS frontend. |
| Optional LLM calls | IMPL_CHOICE | MODIFY | The spec never says which LLM or whether calls leave the machine. Decide this in V1: extraction and drafting via an API with JD text only, no personal documents sent without your explicit action. Your Ollama setup can do extraction offline if you prefer. |

## Sections 48–50. Phases, tests, failure modes

| Item | Type | Verdict | Reason |
|---|---|---|---|
| Phase 0 | PRODUCT | KEEP | This document. |
| Phase 1 core list | PRODUCT | MODIFY | Add "programme timeline" (backward-planned dates from intended start) and "user facts file" (cohort, graduation date, Mandarin level, intended dates). Remove "basic ranking" as numeric; replace with tiers. |
| Phase 2 discovery | PRODUCT | DEFER, reduced | Only company-page collectors with stable endpoints, only for shortlisted companies. |
| Phase 3 intelligence | PRODUCT | MODIFY | Skill evidence YAML and messages move into Phase 1 because they are needed for the first application, which by the timeline may be within weeks. |
| Phase 4 browser assistance | PRODUCT | DEFER indefinitely except capture bookmarklet | See sections 18 and 36. |
| Phase 5 feedback loop | PRODUCT | DEFER | |
| Test list | TECHNICAL | KEEP, prune | Drop tests tied to removed features (fingerprint dedup, autofill, source-staleness diff). Add: "8-month duration against a 6-month cap produces AT_RISK not INCOMPATIBLE and not CONFIRMED"; "prior YES participation UNKNOWN keeps every job at PROGRAMME_CHECK_REQUIRED". |
| Failure-mode list | PRODUCT | KEEP | Add one: assuming a self-sourced internship outside YES can obtain a work permit at all. Standard work-permit criteria (degree plus experience) are not met by an undergraduate; the bilateral scheme is what makes an intern permit possible. This is an inference, see ledger I1, but it changes what "self-sourced" can mean. |

## Missing requirements

M1. A programme timeline. Intended internship start and end dates, SUTD's deadline for company details, and the visa chain (contract → LOC → entry permit → Z visa → arrival → work permit within 15 days → residence permit) planned backwards. This is the requirement that decides how urgent discovery is. Nothing in the spec computes a date.

M2. Explicit user facts file. Graduation cohort (届), expected graduation date, Mandarin level, nationality, prior YES participation status, intended dates. Half the eligibility engine reads these and the spec never says where they come from.

M3. Funding tracking. GRT (Enterprise Singapore), iPREP (IMDA), and Business China stipend matching up to S$1,000 are verified funding routes with their own eligibility and deadlines. One constraint record each.

M4. A decision on where LLM output goes. Every LLM-produced field should be marked as machine-extracted until you confirm it, or the eligibility engine will act on hallucinated cohort years.

## Contradictions inside the spec

X1. Section 17 lists BOSS直聘, 实习僧, 牛客, 脉脉 as collector sources. Section 18 forbids bypassing their login and anti-bot controls. Both cannot hold. Resolved above by making them manual-capture sources only.

X2. Section 31 requires thirteen generated files per shortlisted role. Section 53 says the objective is minimal administrative overhead. Resolved by reducing to four on-demand files.

X3. Section 25 asks for nine scores and section 26 warns that scores must not let a title beat substance. A numeric overall makes that failure easy. Resolved with gates plus tiers.

X4. Section 5 says "do not assume the 12-month GII structure means a 12-month YES internship". Your own stated structure is an 8-month internship, which already exceeds the verified 6-month YES cap. The spec is guarding against the wrong number.
