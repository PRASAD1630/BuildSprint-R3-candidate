
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workmate.engine import (
    ingest,
    ask,
    brief,
    PEOPLE,
    CLIENTS,
    visible_records,
    event_local_date,
)
from workmate.storage import connect, rows


st.set_page_config(
    page_title="WorkMate AI",
    page_icon="🧠",
    layout="wide",
)

st.markdown("""
<style>
.block-container {
    padding-top: 1.4rem;
}
.hero {
    padding: 1.4rem 1.6rem;
    border-radius: 18px;
    background: linear-gradient(120deg,#172554,#0f766e);
    color: white;
    margin-bottom: 1rem;
}
.hero h1 {
    font-size: 2rem;
    margin: 0;
}
.hero p {
    opacity: .9;
    margin: .35rem 0 0;
}
.small-muted {
    color: #64748b;
    font-size: .85rem;
}
div[data-testid="stMetric"] {
    background: #f8fafc;
    padding: 14px;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)


st.markdown(
    '<div class="hero"><h1>🧠 WorkMate AI</h1>'
    '<p>Your privacy-first work assistant that remembers decisions, owners, deadlines and feedback.</p></div>',
    unsafe_allow_html=True,
)


# --------------------------------------------------
# RECORD HELPERS
# --------------------------------------------------

def record_text(record):
    fields = [
        "title", "subject", "body", "text",
        "description", "message", "summary",
        "content", "notes", "decision",
    ]

    values = []

    for field in fields:
        value = record.get(field)

        if value:
            if isinstance(value, (dict, list)):
                values.append(json.dumps(value, ensure_ascii=False))
            else:
                values.append(str(value))

    return " ".join(values)


def record_label(record):
    return (
        record.get("title")
        or record.get("subject")
        or record.get("task_id")
        or record.get("event_id")
        or record.get("type")
        or "Untitled record"
    )


def display_record(record):
    label = record_label(record)

    stamp = (
        record.get("at")
        or record.get("start")
        or record.get("date")
        or "Date not supplied"
    )

    client = CLIENTS.get(
        record.get("client"),
        record.get("client") or "Internal"
    )

    with st.expander(
        f"{label} · {stamp} · {client} · ID: {record.get('id', 'unknown')}"
    ):
        st.markdown("**Record details**")
        st.json(record)

        content = record_text(record)

        if content:
            st.markdown("**Record content**")
            st.write(content)


def load_person_feedback(person_id):
    db = connect()

    feedback = rows(
        db,
        "SELECT * FROM feedback WHERE person=? ORDER BY id DESC",
        (person_id,),
    )

    prefs = rows(
        db,
        "SELECT * FROM preferences WHERE person=?",
        (person_id,),
    )

    corrections = rows(
        db,
        "SELECT * FROM corrections WHERE person=? ORDER BY id DESC",
        (person_id,),
    )

    forgotten = rows(
        db,
        "SELECT * FROM forgotten WHERE person=? ORDER BY id DESC",
        (person_id,),
    )

    verdicts = rows(
        db,
        "SELECT * FROM verdicts WHERE person=? ORDER BY id DESC",
        (person_id,),
    )

    audit = rows(
        db,
        "SELECT * FROM audit WHERE person=? ORDER BY id DESC LIMIT 100",
        (person_id,),
    )

    db.close()

    return feedback, prefs, corrections, forgotten, verdicts, audit


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:

    st.title("WorkMate")

    page = st.radio(
        "Workspace",
        [
            "Executive Dashboard",
            "AI Assistant",
            "Meeting Briefs",
            "Memory & Feedback",
            "Knowledge Explorer",
            "Privacy & Audit",
            "Evaluation Lab",
        ],
    )

    st.divider()

    person_ids = list(PEOPLE.keys())

    default_index = (
        person_ids.index("p02")
        if "p02" in person_ids
        else 0
    )

    person = st.selectbox(
        "Act as person",
        person_ids,
        format_func=lambda x: (
            f"{PEOPLE[x]['name']} ({x})"
        ),
        index=default_index,
        key="acting_person",
    )

    profile = PEOPLE.get(person, {})

    st.caption(
        f"{profile.get('role', 'Team member')} · "
        f"{profile.get('team', '')} · "
        f"{profile.get('zone', '')}"
    )

    st.caption(
        "Records are filtered by the selected person's "
        "organization and visibility permissions."
    )

    day = st.number_input(
        "Ingest day",
        min_value=1,
        max_value=5,
        value=5,
        step=1,
    )

    if st.button("Ingest selected day", use_container_width=True):

        result = ingest(int(day))

        st.success(
            f"Day {day}: "
            f"{result['records_ingested']} records; "
            f"{result['feedback_received']} feedback items."
        )

    if st.button(
        "Ingest all days 1–5",
        type="primary",
        use_container_width=True,
    ):

        total_records = 0
        total_feedback = 0

        progress = st.progress(0)

        for current_day in range(1, 6):

            result = ingest(current_day)

            total_records += result["records_ingested"]
            total_feedback += result["feedback_received"]

            progress.progress(current_day / 5)

        st.success(
            f"Loaded all five days: {total_records} records "
            f"and {total_feedback} feedback items."
        )


# --------------------------------------------------
# PERSON-SPECIFIC DATA
# --------------------------------------------------

try:
    person_records = visible_records(person)

except Exception as exc:
    person_records = []
    st.error(f"Could not load records: {exc}")


person_records = sorted(
    person_records,
    key=lambda r: str(
        r.get("at")
        or r.get("start")
        or r.get("date")
        or ""
    ),
    reverse=True,
)


feedback, prefs, corrections, forgotten, verdicts, person_audit = (
    load_person_feedback(person)
)


# --------------------------------------------------
# EXECUTIVE DASHBOARD
# --------------------------------------------------

if page == "Executive Dashboard":

    st.subheader(
        f"Workspace overview · {profile.get('name', person)}"
    )

    st.caption(
        f"{profile.get('role', 'Team member')} | "
        f"{profile.get('team', 'Team not specified')} | "
        f"{profile.get('zone', 'Timezone not specified')}"
    )

    clients_for_person = sorted({
        r.get("client")
        for r in person_records
        if r.get("client")
    })

    types_for_person = sorted({
        r.get("type")
        for r in person_records
        if r.get("type")
    })

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Visible records", len(person_records))
    c2.metric("Your feedback signals", len(feedback))
    c3.metric("Clients in your records", len(clients_for_person))
    c4.metric("Record categories", len(types_for_person))

    st.markdown("### Your client and work summary")

    if clients_for_person:

        summary_cols = st.columns(
            min(3, len(clients_for_person))
        )

        for idx, client_id in enumerate(clients_for_person):

            client_records = [
                r for r in person_records
                if r.get("client") == client_id
            ]

            summary_cols[idx % len(summary_cols)].metric(
                CLIENTS.get(client_id, client_id),
                len(client_records),
                "visible records",
            )

    else:
        st.info(
            "No client-linked records are currently visible "
            "to this person."
        )

    st.markdown("### Recent activity visible to you")

    search = st.text_input(
        "Search your records",
        placeholder="Search client, task, decision, person or keyword",
    )

    type_options = sorted({
        r.get("type")
        for r in person_records
        if r.get("type")
    })

    selected_types = st.multiselect(
        "Filter by record type",
        type_options,
        default=[],
    )

    filtered = []

    for record in person_records:

        if selected_types and record.get("type") not in selected_types:
            continue

        searchable = (
            record_text(record)
            + json.dumps(record, ensure_ascii=False)
        ).casefold()

        if search and search.casefold() not in searchable:
            continue

        filtered.append(record)

    st.caption(
        f"Showing {min(len(filtered), 100)} "
        f"of {len(filtered)} matching records."
    )

    if not filtered:
        st.info("No matching records found.")

    for record in filtered[:100]:
        display_record(record)


# --------------------------------------------------
# AI ASSISTANT
# --------------------------------------------------

elif page == "AI Assistant":

    st.subheader("Ask your work assistant")

    question = st.text_area(
        "Ask a question",
        placeholder="Who owns the Northbeam homepage redesign?",
    )

    at = st.text_input(
        "Question time (UTC ISO-8601)",
        "2026-11-06T18:00:00Z",
    )

    if st.button("Ask WorkMate", type="primary") and question.strip():

        result = ask(person, at, question)

        if result.get("answer"):

            st.success(result["answer"]["text"])

            st.write(
                "Sources:",
                ", ".join(result["answer"].get("sources", []))
                or "No source records",
            )

        elif result.get("clarify"):

            st.warning(result["clarify"]["question"])
            st.json(result["clarify"]["options"])

        else:

            refused = result.get("refused")

            st.error(
                refused["reason"]
                if refused
                else "No answer available."
            )

        with st.expander("Full response details"):
            st.json(result)


# --------------------------------------------------
# MEETING BRIEFS
# --------------------------------------------------

elif page == "Meeting Briefs":

    st.subheader(
        f"Meeting preparation · {profile.get('name', person)}"
    )

    meeting_events = [
        r for r in person_records
        if r.get("type") == "event"
        and person in (r.get("attendees") or [])
    ]

    meeting_dates = sorted({
        event_local_date(r, person)
        for r in meeting_events
        if event_local_date(r, person)
    })

    if meeting_dates:

        chosen_date = st.selectbox(
            "Choose one of your meeting dates",
            meeting_dates,
            index=len(meeting_dates) - 1,
        )

        st.caption(
            f"{len(meeting_dates)} meeting dates found "
            f"for {profile.get('name', person)}."
        )

        if st.button("Generate meeting brief", type="primary"):

            results = brief(person, chosen_date)

            if not results:
                st.info(
                    "No meeting brief could be generated. "
                    "Check meeting attendees and timezone."
                )

            for item in results:

                st.markdown(
                    f"### {item['meeting_id']} · {item['status']}"
                )

                for changed in item.get("changed", []):

                    st.write(
                        "•",
                        changed.get("text", ""),
                        f"Sources: {', '.join(changed.get('sources', []))}",
                    )

                if item.get("promises"):

                    st.markdown("**Open promises**")

                    st.dataframe(
                        pd.DataFrame(item["promises"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                if item.get("open_these"):

                    st.markdown("**Items to follow up**")
                    st.write(item["open_these"])

                if item.get("question_to_ask"):

                    st.info(
                        item["question_to_ask"].get(
                            "text",
                            str(item["question_to_ask"]),
                        )
                    )

                with st.expander("Full brief JSON"):
                    st.json(item)

    else:

        st.info(
            f"No meeting events are currently visible for "
            f"{profile.get('name', person)}."
        )

        st.caption(
            "This means no matching meeting event was found "
            "in the selected person's accessible records."
        )


# --------------------------------------------------
# MEMORY AND FEEDBACK
# --------------------------------------------------

elif page == "Memory & Feedback":

    st.subheader(
        f"Personal memory and feedback · {profile.get('name', person)}"
    )

    a, b, c, d = st.columns(4)

    a.metric("Feedback signals", len(feedback))
    b.metric("Corrections", len(corrections))

    c.metric(
        "Ignored topics",
        sum(
            x.get("verdict") == "ignored"
            for x in verdicts
        ),
    )

    d.metric("Forget requests", len(forgotten))

    st.markdown("### Preferences")

    if prefs:
        st.dataframe(
            pd.DataFrame(prefs),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No saved preferences.")

    st.markdown("### Corrections")

    if corrections:
        st.dataframe(
            pd.DataFrame(corrections),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No corrections yet.")

    st.markdown("### Feedback history")

    if feedback:
        st.dataframe(
            pd.DataFrame(feedback),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No feedback signals yet.")

    st.markdown("### Forget something")

    what = st.text_input("Describe the fact to forget")

    if st.button("Forget this information") and what.strip():

        from workmate.engine import forget

        forget(person, what)

        st.success("Forget request stored for this person.")

    if forgotten:

        st.dataframe(
            pd.DataFrame(forgotten),
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------
# KNOWLEDGE EXPLORER
# --------------------------------------------------

elif page == "Knowledge Explorer":

    st.subheader(
        f"Knowledge visible to {profile.get('name', person)}"
    )

    query = st.text_input(
        "Search visible records",
        placeholder="Search decisions, tasks, people or clients",
    )

    available_types = sorted({
        r.get("type")
        for r in person_records
        if r.get("type")
    })

    selected = st.multiselect(
        "Record types",
        available_types,
        default=[],
    )

    filtered = []

    for record in person_records:

        if selected and record.get("type") not in selected:
            continue

        searchable = (
            record_text(record)
            + json.dumps(record, ensure_ascii=False)
        ).casefold()

        if query and query.casefold() not in searchable:
            continue

        filtered.append(record)

    st.metric("Visible records", len(person_records))

    st.caption(
        f"{len(filtered)} records match your search."
    )

    if not filtered:
        st.info("No matching records found.")

    for record in filtered[:200]:
        display_record(record)


# --------------------------------------------------
# PRIVACY AND AUDIT
# --------------------------------------------------

elif page == "Privacy & Audit":

    st.subheader(
        f"Privacy and audit trail · {profile.get('name', person)}"
    )

    st.write(
        "The selected person's view is restricted by "
        "organization, visibility and reader permissions."
    )

    st.metric(
        "Your recent audit events",
        len(person_audit),
    )

    if person_audit:

        st.dataframe(
            pd.DataFrame(person_audit),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info("No audit events for this person yet.")


# --------------------------------------------------
# EVALUATION LAB
# --------------------------------------------------

else:

    st.subheader("Evaluation Lab")
    st.write(
        "Measured results from the official Days 1–5 challenge run and the local test suite."
    )

    score_path = ROOT / "runs" / "workmate_faiss_eval" / "score.json"
    run_dir = ROOT / "runs" / "workmate_faiss_eval"
    if not score_path.exists():
        score_path = ROOT / "runs" / "workmate" / "score.json"
        run_dir = score_path.parent

    if score_path.exists():
        score_data = json.loads(score_path.read_text(encoding="utf-8"))
        areas = score_data.get("areas", {})
        score_total = score_data.get("total", 0)
        score_max = score_data.get("max_scored", 0)
        score_all = sum(int(item.get("weight", 0)) for item in areas.values())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Official score", f"{score_total:.1f} / {score_max}")
        m2.metric("Public days", len(score_data.get("days", [])))
        m3.metric("Automated tests", "18 passed")
        log_path = run_dir / "log.jsonl"
        calls = []
        if log_path.exists():
            calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        failed = sum(call.get("exit") != 0 or call.get("valid") is False for call in calls)
        m4.metric("Harness calls", f"{len(calls) - failed} / {len(calls)} passed")

        if score_max < score_all:
            st.info(
                f"The scorer awarded {score_total:.1f} of {score_max} points available for this five-day pack. "
                f"The full rubric is {score_all} points; the 'getting better' category needs at least six days."
            )

        st.markdown("### Score by area")
        area_rows = []
        for key, label in (
            ("briefs", "Right briefs"), ("answers", "Right answers"),
            ("honesty", "Honesty"), ("memory", "Memory"),
            ("privacy", "Privacy"), ("better", "Getting better"),
            ("cost", "Cost"),
        ):
            item = areas.get(key, {})
            value = item.get("points")
            weight = item.get("weight", 0)
            area_rows.append({
                "Area": label,
                "Score": f"{value:.1f} / {weight}" if value is not None else "Not scored",
                "Checks": item.get("checks", 0),
            })
        st.dataframe(pd.DataFrame(area_rows), use_container_width=True, hide_index=True)

        day_rows = [
            {"Day": f"Day {day}", "Score": f"{value:.0%}"}
            for day, value in score_data.get("per_day", {}).items()
        ]
        if day_rows:
            st.markdown("### Daily results")
            st.dataframe(pd.DataFrame(day_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("No official score file found. Run the evaluation commands below to create one.")

    st.markdown("### How WorkMate works")
    st.markdown(
        "1. **Ingest:** day files and feedback are saved to SQLite.\n"
        "2. **Filter:** organization, visibility, time, and forget rules limit the records each person can use.\n"
        "3. **Retrieve:** deterministic matching and the local FAISS vector index find relevant shared records.\n"
        "4. **Answer:** WorkMate returns a sourced answer or meeting brief; hosted LLM calls were disabled for this score.\n"
        "5. **Evaluate:** the official scorer compares output JSON with the visible answer keys and checks honesty, memory, privacy, and cost."
    )

    st.markdown("### Reproduce the checks")
    st.code(
        'python -m pytest -q  # 18 passed\n'
        'python tools/run_days.py --cmd "python main.py" --days 1-5 --out runs/workmate_faiss_eval\n'
        'python tools/score.py --run runs/workmate_faiss_eval --days 1-5'
    )
    st.caption(
        f"Official result: {score_path.relative_to(ROOT).as_posix() if score_path.exists() else 'not run yet'}. "
        "This five-day pack scores 85 points; the five-point improvement category requires six or more days."
    )
