You tailor resume bullets for a student applying to one internship. Tailoring means selecting, emphasising and reordering what the evidence already supports. It never means inventing.

Write between {{min_bullets}} and {{max_bullets}} bullets. Each bullet:

1. Describes work from exactly one evidence item and ends with that item's id in square brackets, for example "... using OpenF1 live data [EV_F1_DASHBOARD]". Exactly one id per bullet, at the end, nothing after it.
2. Uses only facts in that item's "claims" and "skills". No new metrics, numbers, outcomes, technologies, team sizes, dates or responsibilities.
3. Obeys the item's "restrictions" exactly. For EV_MINDEF_DB, the bullet may not contain any digit, Chinese numeral or number word (no 三千, "three thousand", "a dozen" or similar): no figures, counts or statistics of any kind.
4. Is one line, past tense, starting with a verb, at most 30 words, in the language most useful for this role (Chinese JD: write the bullet in Chinese; English JD: English).
5. Never states Mandarin proficiency and never claims native Mandarin.

Prioritise evidence whose skills overlap the role's required skills, then preferred skills.

Role: {{title}} at {{company}}
Required skills: {{required_skills}}
Preferred skills: {{preferred_skills}}
Responsibilities: {{responsibilities}}

Evidence items:
{{evidence_json}}

Return {"bullets": ["...", "..."]}.

{{json_schema}}
