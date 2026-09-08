"""Single-page, read-mostly Streamlit dashboard.

Run: streamlit run app.py

Blocks: programme status, jobs, next actions, capture. No job editing and no confirmation loop
here; those stay in the CLI. Nothing on this page sends anything to an external party.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import select

from internship_os import capture as capture_mod
from internship_os.cli import job_show_lines
from internship_os.config import ConfigError, load_config
from internship_os.db import get_engine, get_session, init_db
from internship_os.llm import LLMError
from internship_os.models import Job
from internship_os.programme import constraint_warnings, global_dimensions
from internship_os.schemas import NON_TERMINAL_STATUSES, SourceChannel
from internship_os.tiering import sort_jobs
from internship_os.timeline import build_timeline, placeholders_in_use, top_line

st.set_page_config(page_title="China Internship OS", layout="wide")
st.title("China Internship OS")

try:
    cfg = load_config()
except ConfigError as exc:
    st.error("Configuration is invalid.")
    st.code(exc.format())
    st.stop()

today = date.today()
init_db(get_engine())
session = get_session()

# --------------------------------------------------------------------------------------
# Block 1: programme status
# --------------------------------------------------------------------------------------
st.header("1. Programme status")
steps = build_timeline(cfg.user_facts, cfg.constraints, None, today)
st.subheader(top_line(steps, today))
ids = placeholders_in_use(steps)
st.caption("Placeholder constraint ids: " + (", ".join(ids) if ids else "none"))

constraint_rows = pd.DataFrame(
    [
        {
            "id": c.constraint_id,
            "status": c.status.value,
            "date_verified": c.date_verified,
            "next_verification_date": c.next_verification_date,
            "past_due": c.verification_is_past(today),
        }
        for c in cfg.constraints
    ]
)


def _highlight_past_due(row: pd.Series) -> list[str]:
    style = "background-color: #ffd6d6; color: #7a0000;" if row["past_due"] else ""
    return [style] * len(row)


st.dataframe(
    constraint_rows.style.apply(_highlight_past_due, axis=1),
    width="stretch",
    hide_index=True,
)
for warning in constraint_warnings(cfg.constraints, today):
    st.warning(warning)

st.markdown("**Global programme dimensions (user route, no host assumed)**")
for name, d in global_dimensions(cfg.constraints, cfg.user_facts, today).items():
    st.write(f"- {name}: **{d['status']}** — {d['note']}")
st.write("- SUTD_APPROVAL, HOST_COMPANY and DURATION_AND_DATES are evaluated per job.")

# --------------------------------------------------------------------------------------
# Block 2: jobs
# --------------------------------------------------------------------------------------
st.header("2. Jobs")
jobs = list(session.scalars(select(Job)))
jobs = sort_jobs(jobs, cfg.user_facts)


def _options(values: list[str]) -> list[str]:
    return sorted({v for v in values if v})


col1, col2, col3, col4 = st.columns(4)
tier_f = col1.multiselect("tier", _options([j.tier for j in jobs]))
status_f = col2.multiselect("status", _options([j.status for j in jobs]))
track_f = col3.multiselect("track", _options([j.track for j in jobs]))
city_f = col4.multiselect("city", _options([j.city_zh or "" for j in jobs]))

shown = [
    j
    for j in jobs
    if (not tier_f or j.tier in tier_f)
    and (not status_f or j.status in status_f)
    and (not track_f or j.track in track_f)
    and (not city_f or (j.city_zh or "") in city_f)
]
job_rows = pd.DataFrame(
    [
        {
            "id": j.id,
            "tier": j.tier,
            "company": j.company.display_name if j.company else "",
            "title": j.display_title,
            "city": j.city_zh or "",
            "track": j.track,
            "status": j.status,
            "eligibility": j.eligibility,
            "programme_overall": j.programme_overall,
            "deadline": j.deadline,
            "next_action_date": j.next_action_date,
        }
        for j in shown
    ]
)
if job_rows.empty:
    st.info("No jobs yet. Capture one below, then run `ios confirm <id>`.")
else:
    event = st.dataframe(
        job_rows,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="jobs_table",
    )
    selected_rows = getattr(getattr(event, "selection", None), "rows", []) or []
    if selected_rows:
        selected = shown[selected_rows[0]]
        st.code("\n".join(job_show_lines(selected, cfg)), language=None)

# --------------------------------------------------------------------------------------
# Block 3: next actions
# --------------------------------------------------------------------------------------
st.header("3. Next actions")
active = [j for j in jobs if j.status in NON_TERMINAL_STATUSES and j.next_action_date is not None]
active.sort(key=lambda j: (j.next_action_date, j.id))
if not active:
    st.write("No active next actions.")
for j in active:
    overdue = j.next_action_date <= today
    marker = "OVERDUE" if overdue else "due"
    line = f"{marker} {j.next_action_date} — job {j.id} {j.display_title}: {j.next_action}"
    (st.error if overdue else st.write)(line)

# --------------------------------------------------------------------------------------
# Block 4: capture
# --------------------------------------------------------------------------------------
st.header("4. Capture")
with st.form("capture_form"):
    text = st.text_area("Job description text", height=220)
    source = st.selectbox("Source channel", [s.value for s in SourceChannel])
    submitted = st.form_submit_button("Capture")

if submitted:
    if not text.strip():
        st.error("Paste the job description text first.")
    else:
        try:
            job = capture_mod.capture(text, None, source, session=session, config=cfg, today=today)
            st.success(f"Captured job {job.id}.")
            st.code(f"ios confirm {job.id}", language=None)
        except capture_mod.DuplicateCaptureNeedsDecision as dup:
            st.warning("Possible duplicate; nothing was saved. Existing job(s): " + ", ".join(str(i) for i in dup.candidate_ids))
            for job_id in dup.candidate_ids:
                existing = session.get(Job, job_id)
                if existing is not None:
                    st.write(f"- job {existing.id}: {existing.display_title} [{existing.status}]")
            st.info("Resolve it in the CLI: `ios capture --paste --source <channel>` offers attach / create new / cancel.")
            st.session_state["pending_duplicate"] = {
                "text": dup.text,
                "source": dup.source_channel,
                "extracted": dup.extracted.model_dump(mode="json"),
            }
        except (capture_mod.CaptureError, LLMError) as exc:
            st.error(str(exc))

pending = st.session_state.get("pending_duplicate")
if pending and st.button("Create as a separate new job anyway"):
    from internship_os.schemas import ExtractedJob

    job = capture_mod.capture(
        pending["text"],
        None,
        pending["source"],
        session=session,
        config=cfg,
        today=today,
        extracted=ExtractedJob.model_validate(pending["extracted"]),
        force_new=True,
    )
    st.session_state.pop("pending_duplicate", None)
    st.success(f"Captured job {job.id}.")
    st.code(f"ios confirm {job.id}", language=None)
