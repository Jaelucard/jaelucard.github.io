# ASSUMPTION_LEDGER.md
China Internship OS. Compiled 2026-09-07 (all sources accessed that day).

Statuses: VERIFIED, USER_CONFIRMED, LIKELY, UNVERIFIED, CONFLICTING, OUTDATED, REQUIRES_CONFIRMATION.
Evidence strength: STRONG (primary official source, current), MEDIUM (official but possibly stale, or reputable secondary), WEAK (agency, forum, inference).

Sources used:
- S1 YES portal home and process page, https://yes.businesschina.org.sg/ (page modified 2026-09-07)
- S2 YES For Companies page and FAQ, https://yes.businesschina.org.sg/for-companies/ (page modified 2025-04-29)
- S3 YES About page, https://yes.businesschina.org.sg/about-us/
- S4 Business China article, YES vs self-sourced, https://businesschina.org.sg/youth-internship-exchange-singapore-china/ (July 2026)
- S5 SUTD Career Development student FAQ, https://www.sutd.edu.sg/campus-life/career-development/student/
- S6 SUTD GEXP page, https://www.sutd.edu.sg/campus-life/global-experience-and-exchange/student-exchange/outbound/global-exchange-programme-gexp/ (Aug 2026)
- S7 SUTD DGIT page, https://www.sutd.edu.sg/campus-life/global-experience-and-exchange/sutd-dgi/1-term/
- S8 China NIA residence-permit service guide, https://s.nia.gov.cn/mps/bszy/wgrcrjEn/e-sqwgrjlzj/202201/ and https://en.nia.gov.cn/n147423/n147478/n147715/c158215/content.html
- S9 Baker McKenzie China immigration resource hub (secondary), https://resourcehub.bakermckenzie.com/en/resources/global-immigration-and-mobility/asia-pacific/china/topics/employment-assignments
- U Your own statements recorded in earlier conversations.

## Resolutions recorded 2026-09-07 (supersede the rows below)

All entries in this section are USER_CONFIRMED: relayed by you from SUTD and Business China, not seen in writing by this audit. Where a written reply exists, attach it to the constraint record; a forwarded email raises the status to VERIFIED for the cohort.

| Row | New status | Resolution |
|---|---|---|
| A3 | USER_CONFIRMED (school and YES both confirmed) | The DGIT internship at MolarData was a ZJU-hosted programme element, not a YES placement. YES is open to you. YES_ELIGIBILITY dimension becomes CONFIRMED globally. |
| A7, A8 | USER_CONFIRMED route | SUTD and Business China handle host onboarding between them. Your obligation is to obtain an offer from a company that is not on their blacklist and return to SUTD for instructions. Onboarding lead time is still not stated. See new row N1. |
| B1, B4 | RESOLVED | The placement is at most 6 months. SUTD baseline is one 4-month internship. Intended window: after Chinese New Year 2027 to the 6-month limit. DURATION gate: minimum 4 months, maximum 6 months. Actual start is negotiated per company. |
| B2 | USER_CONFIRMED | Self-sourcing confirmed. |
| B3 | USER_CONFIRMED | Route is YES. |
| B5, B7 | RESOLVED | GII and the SUTD internship requirement run concurrently; admin handled between you and SUTD. No SUTD hard deadline for company details, provided visa and offer are settled before the exchange ends in mid-January 2027. Your personal deadline for an offer in hand: second week of December 2026. |
| B6 | USER_CONFIRMED preference, not rule | SUTD prefers a startup or a subsidiary of a larger company. Large companies are permitted. Strategy: startups first, subsidiaries and large companies as fallback. |
| C4 | USER_CONFIRMED plan | You will return to Singapore after the exchange, obtain the Z visa at the embassy, then re-enter and start. |
| C3 | Moot | In-country conversion is no longer needed. |

New rows:

| ID | Assumption | Category | Importance | Evidence | Status | Next action |
|---|---|---|---|---|---|---|
| N1 | SUTD and/or Business China maintain a blacklist of host companies | PROGRAMME | High | Your statement | USER_CONFIRMED existence, UNVERIFIED contents | Ask whether you can see the list or submit a company name for a check before investing in an application (OPEN_QUESTIONS Q8). |
| N2 | Chinese New Year 2027 falls on 6 February 2027, with the public holiday running roughly one week | PROGRAMME | Medium | Calendar knowledge; the State Council publishes the official 2027 holiday schedule around Nov–Dec 2026 | LIKELY | Confirm holiday dates when published; intended start is the first working week after. |
| N3 | Z-visa processing time varies by province | USER FACT | Medium | Your understanding | CONFLICTING with the process | The Z visa itself is issued by the Chinese Embassy in Singapore on a standard timeline. The step that varies by province is the host's application for the entry permit (work permit notice) at the local work-permit authority, because that authority is provincial or municipal. Plan the provincial variation into the host's step, not the embassy step. |
| N4 | Time needed between offer and Z visa in hand | PROGRAMME | High | Not stated by anyone | REQUIRES_CONFIRMATION | Ask Business China for typical LOC and entry-permit durations for Zhejiang and Shanghai hosts (OPEN_QUESTIONS Q9). |

## A. Programme scheme (YES)

| ID | Assumption | Category | Importance | Evidence | Strength | Auth. source needed | Status | Impact if false | Dev can proceed? | Next action |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | YES allows a Singaporean youth to intern in China for up to 6 months | PROGRAMME | Critical | S1, S3, S4 all state "up to 6 months" | STRONG | Business China | VERIFIED | Duration gate is wrong | Yes | Encode as constraint YES_MAX_DURATION = 6 months, re-verify 2027-01-01 |
| A2 | You are eligible for YES as a Singapore citizen studying full-time at an AU | PROGRAMME | Critical | S2 FAQ: Singapore citizens at AUs or polys, or graduated within one calendar year | STRONG on the rule; your citizenship and enrolment are U | VERIFIED rule, USER_CONFIRMED facts | Whole scheme closed | Yes | None beyond A3 |
| A3 | You have not previously participated in YES | PROGRAMME | Critical | S2 FAQ: eligible youths are those "who have not participated in the Scheme previously". U: you interned at MolarData Oct–Dec 2025 under DGIT. S2 FAQ separately says IHL work-study attachments run on student visas, which suggests DGIT internships are not YES placements, but this is not stated. | MEDIUM | SUTD CDC or Business China | REQUIRES_CONFIRMATION | YES is unavailable; compliance subsystem must be re-pointed to the school-arranged work-study route | Yes for tracker; No for compatibility engine | Ask Q2 |
| A4 | The intern's process is: application → interview → host issues internship contract → school applies for LOC from Business China → host applies for entry permit at the work-permit authority → intern applies for Z visa at the Chinese Embassy in Singapore → arrival → medical → work permit within 15 days if ≥ 90 days → residence permit | PROGRAMME | Critical | S1 process page | STRONG | Business China | VERIFIED | Timeline model wrong | Yes | Encode as ordered steps in the timeline model |
| A5 | Host obligations under YES: appropriate stipend (amount set by host), conducive environment, designated supervisor with periodic reviews, feedback to Business China after the stint | PROGRAMME | High | S2 | STRONG | Business China | VERIFIED | Employer explanation pack wrong | Yes | Use in yes-explanation draft |
| A6 | Intern bears airfare, insurance, accommodation; medical exam cost is at host discretion | PROGRAMME | Medium | S2 | STRONG | Business China | VERIFIED | Budget wrong | Yes | Note in logistics |
| A7 | Students may source a placement via YES listings or via "current internship programmes arranged by their respective schools" | PROGRAMME | Critical | S2 FAQ | STRONG for the sentence; its meaning for a student-sourced company is not stated | Business China + SUTD | VERIFIED text, REQUIRES_CONFIRMATION applicability | Self-sourced onboarding route unknown | Yes | Ask Q3 |
| A8 | A company joins YES by signing up on the YES portal and listing opportunities with Business China | PROGRAMME | High | S2 "How to onboard" | STRONG for the portal route; unknown whether it is the only route | Business China | VERIFIED as one route | Onboarding lead time unknown | Yes | Ask Q3 |
| A9 | Visa type under YES is a Z visa leading to a work permit and residence permit | PROGRAMME | Critical | S1 process page says Z visa and Work Permit for Foreigners. S2 FAQ says "internship visa", "more details in due course" | CONFLICTING within the same site; S1 is the more recently modified page and more specific | Business China / Chinese Embassy Singapore | CONFLICTING, treat S1 as current | Immigration steps wrong | Yes | Confirm with Business China when asking Q4 |
| A10 | Business China assists with the visa application and issues the LOC | PROGRAMME | High | S2, S4 | STRONG | Business China | VERIFIED | | Yes | |
| A11 | Funding: GRT (Enterprise Singapore), iPREP (IMDA), Business China stipend matching up to S$1,000 case by case | PROGRAMME | Medium | S2 | MEDIUM (linked programmes have their own rules not checked) | ESG, IMDA, Business China | VERIFIED as listed | Money left unclaimed | Yes | One constraint record each, check each programme's own page |
| A12 | Implementing agencies in China are MOHRSS and the National Center of Human Resources Mobility | PROGRAMME | Low | S2 | STRONG | | VERIFIED | | Yes | |

## B. SUTD GII and your cohort

| ID | Assumption | Category | Importance | Evidence | Strength | Auth. source needed | Status | Impact if false | Dev can proceed? | Next action |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | GII = 4-month GEXP at ZJU followed by an 8-month internship in Hangzhou/Shanghai, one year total | USER FACT | Critical | U. S6 confirms the pattern "GEXP Fall (after Term 5), then internship". S5 says SUTD's Spring internship period is Jan–Aug (6–8 months). No public SUTD page describes a programme named GII. | MEDIUM | SUTD GII administrators | USER_CONFIRMED structure, UNVERIFIED name and rules | Duration and date gates wrong | Yes | Ask Q1 and Q5 |
| B2 | The internship must be self-sourced | USER FACT | High | U | Your statement only | SUTD | USER_CONFIRMED | Discovery effort misdirected if SUTD provides placements | Yes | Confirm in Q3 |
| B3 | The internship will run through YES | USER FACT | Critical | U. S2 FAQ says YES targets students interning "without studying in a Chinese university campus", while GII combines both. That is a description of the scheme's intent, not an exclusion. | MEDIUM | SUTD, Business China | USER_CONFIRMED intent, REQUIRES_CONFIRMATION that this cohort's route is YES rather than the IHL work-study route on a student visa | Wrong scheme modelled | Yes | Ask Q1, Q3 |
| B4 | An 8-month internship can be completed under YES | INFERENCE from B1 + A1 | Critical | A1 caps YES at 6 months | STRONG that the two numbers conflict | SUTD | CONFLICTING | Either the internship is ≤ 6 months, or only part of it is under YES, or the 8-month figure is the SUTD internship window rather than the placement length | Yes for everything except DURATION gate | Ask Q1 first. Encode DURATION as AT_RISK for any placement longer than 6 months. |
| B5 | SUTD's official internship minimum is 16 weeks and one internship is a graduation requirement | PROGRAMME | High | S5 | STRONG for the ordinary internship; whether GII uses the same minimum is unknown, as the spec itself warns | SUTD | VERIFIED for ordinary internship, UNVERIFIED for GII | Minimum-duration gate wrong | Yes | Ask Q7 |
| B6 | Host must be a "startup" | USER FACT (from your description) | High | U says "internship at a Chinese startup". S7 shows the earlier DGIT placed students in "start-ups and innovation companies". Unknown whether GII restricts host type. | WEAK | SUTD | REQUIRES_CONFIRMATION | Large-company watchlist entries are out of scope | Yes | Ask Q6 |
| B7 | SUTD needs company details some weeks or months before the start date | INFERENCE | High | A4 shows a five-step chain before arrival, each with a dependency; S5 says an internship briefing happens about a month before ordinary internships start | MEDIUM | SUTD | REQUIRES_CONFIRMATION | You discover roles too late to complete the LOC and visa chain | Yes | Ask Q5. Until answered, plan for offers to be in hand two months before the intended start. |
| B8 | Your graduation cohort year (届) and expected graduation date | USER FACT | Critical | Not on record | none | You | UNVERIFIED | Cohort hard-fail is wrong on every job | No for eligibility engine | State it in the user facts file |
| B9 | Your Mandarin working level | USER FACT | High | Profile says you speak Chinese; no level stated | none | You | UNVERIFIED | Messages overclaim | Yes | State it |

## C. Immigration

| ID | Assumption | Category | Importance | Evidence | Strength | Auth. source needed | Status | Impact if false | Dev can proceed? | Next action |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | The standard basis for a work-type residence permit is entry on a Z visa; entrants on other visa types must meet high-level talent, urgently needed specialist, or investor criteria | PROGRAMME | Critical | S8 | STRONG | NIA | VERIFIED | | Yes | |
| C2 | The YES process expects the Z visa to be obtained at the Chinese Embassy in Singapore | PROGRAMME | Critical | S1 | STRONG as the documented path | Business China | VERIFIED as the documented path | | Yes | |
| C3 | In-country conversion from another status to a work permit exists in some cities for some cases (M-visa holders in Beijing/Shanghai/Shenzhen, graduates of Chinese universities holding X1) at local PSB discretion | PROGRAMME | High | S9, plus lower-authority agency pages | MEDIUM | Local PSB / Business China | LIKELY that exceptions exist, UNVERIFIED that any applies to an exchange student in Hangzhou | Transition plan assumes an option that does not exist | Yes | Ask Q4 |
| C4 | You will have to exit China at the end of the exchange, obtain the Z visa in Singapore, and re-enter | INFERENCE from C1 + C2 + C3 | Critical | Default reading of the documented path | MEDIUM | Business China, Chinese Embassy Singapore | LIKELY | Time and cost planning wrong; if true and unplanned, the internship start slips | Yes | Ask Q4. Encode IMMIGRATION_COMPATIBILITY as UNKNOWN for all jobs until answered. Plan a return trip as the default. |
| C5 | Your exchange status is a student visa (X1 or X2) | INFERENCE | High | 4-month exchange; X2 is for ≤ 180 days | WEAK (not checked) | Your passport | UNVERIFIED | Which conversion rules apply | Yes | Record actual visa type and expiry in the user facts file |
| C6 | For an internship of 90 days or more, the work permit must be applied for within 15 days of arrival, then a residence permit | PROGRAMME | High | S1 | STRONG | Business China | VERIFIED | | Yes | Timeline step |
| C7 | A medical check-up is required on arrival | PROGRAMME | Medium | S1 | STRONG | Business China | VERIFIED | | Yes | Timeline step |

## D. Market and employer

| ID | Assumption | Category | Importance | Evidence | Strength | Auth. source needed | Status | Impact if false | Dev can proceed? | Next action |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | A self-sourced internship outside YES (or a school-arranged scheme) is unlikely to obtain a work permit, because ordinary work-permit categories require a degree plus experience an undergraduate does not have; the bilateral scheme is what makes an intern permit possible | INFERENCE | Critical | S8, S9 describe standard categories; S2 FAQ says the internship visa "is only available to countries that have a bilateral agreement" | MEDIUM | Business China / host HR | LIKELY | "Self-sourced" would then mean "self-sourced host that then enters YES", never "outside YES" | Yes | Treat any host unwilling to enter YES (or the school route) as HOST_COMPANY_COMPATIBILITY = INCOMPATIBLE once Q3 confirms the route |
| D2 | 实习僧, BOSS直聘, 牛客, 脉脉 require login and prohibit scraping | TECHNICAL | High | General knowledge of the platforms; not re-checked | MEDIUM | Each platform's terms | LIKELY | Automated collectors would be allowed | Yes | No action needed since collectors are removed |
| D3 | Referrals (内推) materially help at large Chinese tech firms | MARKET | Medium | General knowledge | WEAK | Per company | LIKELY | Referral effort wasted | Yes | Record per company as learned |
| D4 | Hangzhou, Shanghai, Suzhou, Nanjing, Wuxi are cities where YES hosts already exist | MARKET | Medium | S1 portal city filter lists all five | STRONG | | VERIFIED | | Yes | |
| D5 | Singapore citizens can enter China visa-free for short stays under the mutual exemption | PROGRAMME | Medium | Not searched in this audit | none | Chinese Embassy Singapore | UNVERIFIED (widely reported, not checked here) | Gap planning between exchange and internship | Yes | Check the embassy page before relying on it |

## E. Implementation assumptions in the spec

| ID | Assumption | Category | Status | Note |
|---|---|---|---|---|
| E1 | A numeric overall score will rank well | IMPL_CHOICE | UNVERIFIED and contradicted by the spec's own section 26 | Replaced with tiers |
| E2 | Twelve relational entities are needed in V1 | IMPL_CHOICE | UNVERIFIED | Five suffice |
| E3 | Automated discovery is the main source of leads | IMPL_CHOICE | UNVERIFIED and contrary to sections 18–19 | Manual capture is the main source |
| E4 | Source-diff rule refresh is feasible | IMPL_CHOICE | UNVERIFIED, likely false for WordPress marketing pages | Replaced with verification dates |

## Still unverified after your answers

- Blacklist contents or a way to check a company against it (N1).
- Typical LOC and entry-permit durations, which set how far before 11 December 2026 an offer must really be signed (N4).
- Your cohort year, expected graduation date, Mandarin level, and exchange visa type and expiry (B8, B9, C5). These are user facts; only you can supply them.
- Written confirmation of the relayed answers. All resolutions above are USER_CONFIRMED until an email from SUTD or Business China is attached.
