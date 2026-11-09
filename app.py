"""Supply Chain Copilot - chat with the procurement database.

Run from the project folder:  streamlit run app.py
Needs ANTHROPIC_API_KEY in a .env file in this folder.
"""
import os
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from src.agent import ask
from src.evals import PRICE_IN, PRICE_OUT

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
st.set_page_config(page_title="Supply Chain Copilot", page_icon="📦")

EXAMPLES = [
    "Which suppliers were late most often, and by how many days?",
    "Which open POs are past due, and what are they worth?",
    "Is any carrier really worse than the others?",
    "How much did we spend with overseas suppliers in Q4?",
]


@st.cache_resource
def get_client():
    return anthropic.Anthropic()


st.title("📦 Supply Chain Copilot")
st.caption("Ask about suppliers, purchase orders and shipments (2025 data, as of Dec 31). "
           "Claude writes and runs read-only SQL; every query is shown so you can check its work.")

if not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant"):
    st.error("No API key found. Add ANTHROPIC_API_KEY=... to a .env file in this folder, then restart.")
    st.stop()

if "history" not in st.session_state:
    st.session_state.history = []      # list of {"question", "answer", "queries", "cost"}
    st.session_state.total_cost = 0.0

with st.sidebar:
    st.header("Try asking")
    for example in EXAMPLES:
        if st.button(example):
            st.session_state.pending = example


def show(turn: dict) -> None:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        if turn["queries"]:
            with st.expander(f"SQL used ({len(turn['queries'])} queries) · ${turn['cost']:.3f}"):
                for sql in turn["queries"]:
                    st.code(sql, language="sql")


for turn in st.session_state.history:
    show(turn)

question = st.chat_input("Ask a question about your supply chain data")
question = question or st.session_state.pop("pending", None)

if question:
    with st.spinner("Querying the database..."):
        try:
            result = ask(question, get_client())
        except anthropic.APIError as exc:
            st.error(f"The API call failed: {exc}")
            st.stop()
    cost = (result.input_tokens * PRICE_IN + result.output_tokens * PRICE_OUT) / 1_000_000
    turn = {"question": question, "answer": result.text, "queries": result.queries, "cost": cost}
    st.session_state.history.append(turn)
    st.session_state.total_cost += cost
    show(turn)

# Sidebar footer goes last, so the cost includes the question just answered.
with st.sidebar:
    st.divider()
    st.metric("Session cost", f"${st.session_state.total_cost:.3f}")
    if st.button("Clear chat"):
        st.session_state.history = []
        st.session_state.total_cost = 0.0
        st.rerun()