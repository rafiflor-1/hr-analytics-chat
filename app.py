"""Streamlit chat UI for the HR data agent.   Run with:  streamlit run app.py"""
import hmac
import os

import streamlit as st

st.set_page_config(page_title="HR Data Chat", page_icon="💬", layout="centered")

# On Streamlit Community Cloud, settings come from the app's Secrets; copy them into
# the environment so the rest of the code reads them the same way as on a laptop.
try:
    for _key, _value in st.secrets.items():
        if isinstance(_value, str):
            os.environ.setdefault(_key, _value)
except Exception:  # no secrets file when running locally
    pass

import agent  # noqa: E402  (must come after the secrets are loaded)
import db  # noqa: E402

MAX_QUESTIONS_PER_SESSION = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "40"))


def require_password() -> None:
    """Block the app behind APP_PASSWORD when one is configured (public deployments)."""
    expected = os.getenv("APP_PASSWORD")
    if not expected or st.session_state.get("authenticated"):
        return
    st.title("HR Data Chat")
    with st.form("login"):
        entered = st.text_input("Access password", type="password")
        if st.form_submit_button("Enter"):
            if hmac.compare_digest(entered, expected):
                st.session_state.authenticated = True
                st.rerun()
            st.error("Incorrect password.")
    st.stop()


require_password()

SAMPLE_QUESTIONS = [
    "What was the annual turnover rate in each year, and which year was worst?",
    "Which departments have the most high-risk active employees?",
    "Who are the top 5 employees by excessive-overtime days, and what department are they in?",
    "Which department has the highest late-arrival rate, and how does it compare to the company average?",
    "What are the top reasons people leave, split by resignation vs involuntary?",
]

st.title("HR Data Chat")
st.caption(
    f"Ask questions about the HR data behind the Tableau dashboards. "
    f"Source: {'Snowflake' if db.backend() == 'snowflake' else 'local extract (DuckDB)'} · "
    f"data through {agent.AS_OF_DATE}"
)

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error(
        "ANTHROPIC_API_KEY is not set. Add it to your environment, or to the app's Secrets "
        "on Streamlit Community Cloud (see README), and restart."
    )
    st.stop()

try:
    db.schema()
except Exception as exc:  # data missing or Snowflake connection failed
    st.error(f"Could not open the data source: {exc}")
    st.stop()

if "turns" not in st.session_state:
    st.session_state.turns = []  # [{'question', 'answer': agent.Answer}]


def show_queries(answer: agent.Answer) -> None:
    if not answer.queries:
        return
    with st.expander(f"Show the SQL ({len(answer.queries)} quer{'y' if len(answer.queries) == 1 else 'ies'})"):
        for i, q in enumerate(answer.queries, 1):
            if q.purpose:
                st.markdown(f"**{i}. {q.purpose}**")
            st.code(q.sql, language="sql")
            if q.error:
                st.warning(q.error)
            elif q.result is not None:
                st.dataframe(q.result, use_container_width=True, hide_index=True)


with st.sidebar:
    st.subheader("Try asking")
    clicked = None
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True):
            clicked = q
    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.turns = []
        st.rerun()
    with st.expander("Tables available"):
        for table, cols in db.schema().items():
            st.markdown(f"**{table}** · {len(cols)} columns")

for turn in st.session_state.turns:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"].text)
        show_queries(turn["answer"])

question = st.chat_input("Ask about turnover, flight risk, attendance…") or clicked
if question and len(st.session_state.turns) >= MAX_QUESTIONS_PER_SESSION:
    st.warning("This session has reached its question limit. Reload the page to start again.")
    question = None
if question:
    with st.chat_message("user"):
        st.markdown(question)
    history = []
    for turn in st.session_state.turns[-6:]:  # keep recent context only
        history.append({"role": "user", "content": turn["question"]})
        history.append({"role": "assistant", "content": turn["answer"].text})
    with st.chat_message("assistant"):
        with st.spinner("Querying the data…"):
            try:
                answer = agent.ask(question, history)
            except Exception as exc:
                answer = agent.Answer(f"Something went wrong calling the model: {exc}")
        st.markdown(answer.text)
        show_queries(answer)
    st.session_state.turns.append({"question": question, "answer": answer})
