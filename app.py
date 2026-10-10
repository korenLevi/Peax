"""Streamlit chat UI for the Airport Investment Intelligence Agent.

    streamlit run app.py

Voice input uses the browser's Web Speech API (Chrome) through streamlit-mic-recorder.
Voice output uses the browser's speechSynthesis. Neither needs an external key.
"""
from __future__ import annotations

import json
import re

import streamlit as st
import streamlit.components.v1 as components

from agent import config as C
from agent import tools
from agent.agent import AirportAgent
from agent.cli import EXAMPLES

st.set_page_config(page_title="Airport Investment Agent", page_icon="🛫", layout="wide")
# Hide Streamlit's built-in Deploy button and the "File change: Rerun" prompt; neither is part of this app.
st.markdown("<style>[data-testid='stAppDeployButton'],[data-testid='stStatusWidget']{display:none;}</style>",
            unsafe_allow_html=True)

try:
    from streamlit_mic_recorder import speech_to_text
except Exception:  # component missing: text chat still works
    speech_to_text = None


# ---------------------------------------------------------------- state
def get_agent() -> AirportAgent:
    if "agent" not in st.session_state:
        st.session_state.agent = AirportAgent()
        st.session_state.turns = []  # [{"role", "text", "tool_calls"}]
    return st.session_state.agent


agent = get_agent()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛫 Airport Investment Agent")
    st.caption("Deterministic scoring over FAA, BTS and OurAirports data. Claude only narrates.")

    model = st.text_input("Claude model", value=agent.model)
    agent.model = model.strip() or C.MODEL

    st.subheader("Scoring weights")
    demand_share = st.slider("Demand vs strain", 0.0, 1.0, float(agent.params.demand_share), 0.05,
                             help="Share of the score coming from demand pressure; the rest is capacity strain.")
    with st.expander("Demand components"):
        dw = {k: st.slider(k, 0.0, 1.0, float(v), 0.05, key=f"dw_{k}") for k, v in C.DEMAND_WEIGHTS.items()}
    with st.expander("Strain components"):
        sw = {k: st.slider(k, 0.0, 1.0, float(v), 0.05, key=f"sw_{k}") for k, v in C.STRAIN_WEIGHTS.items()}

    def _norm(w):
        s = sum(w.values())
        return {k: v / s for k, v in w.items()} if s else w

    agent.params = tools.ScoringParams(_norm(dw), _norm(sw), demand_share)

    st.subheader("Voice")
    speak = st.toggle("Read answers aloud", value=False)
    st.caption("Voice input works in Chrome. The mic button appears above the chat box.")

    if st.button("Show methodology"):
        st.json(tools.run_tool("explain_methodology", {}, agent.params)["data"])
    if st.button("Reset conversation"):
        agent.reset()
        st.session_state.turns = []
        st.rerun()

    st.subheader("Example questions")
    for ex in EXAMPLES:
        if st.button(ex, key=f"ex_{ex[:20]}"):
            st.session_state.pending = ex

# ---------------------------------------------------------------- helpers
def to_speech(md: str, limit: int = 1500) -> str:
    lines = [ln for ln in md.splitlines() if not ln.strip().startswith("|")]
    text = "\n".join(lines)
    text = re.sub(r"[#*`_>]+", "", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def speak_js(text: str):
    components.html(f"""<script>
      const u = new SpeechSynthesisUtterance({json.dumps(text)});
      u.lang = 'en-US'; u.rate = 1.0;
      window.parent.speechSynthesis.cancel();
      window.parent.speechSynthesis.speak(u);
    </script>""", height=0)


def render_turn(t: dict):
    with st.chat_message(t["role"]):
        st.markdown(t["text"])
        if t.get("tool_calls"):
            with st.expander(f"Data & assumptions ({len(t['tool_calls'])} tool call(s))"):
                for c in t["tool_calls"]:
                    st.markdown(f"**{c['name']}** `{json.dumps(c['input'])}`")
                    st.json(c["result"], expanded=False)


# ---------------------------------------------------------------- chat
st.markdown("Ask about US airport expansion candidates, congestion, long haul mix, or unmet demand. "
            "Every number comes from a deterministic tool; see *Data & assumptions* under each answer.")

for t in st.session_state.turns:
    render_turn(t)

voice_text = None
if speech_to_text is not None:
    voice_text = speech_to_text(language="en", start_prompt="🎤 Speak", stop_prompt="⏹ Stop",
                                just_once=True, use_container_width=False, key="stt")

typed = st.chat_input("e.g. Which airports in New England are strong candidates for terminal expansion?")
question = typed or voice_text or st.session_state.pop("pending", None)

if question:
    st.session_state.turns.append({"role": "user", "text": question})
    render_turn(st.session_state.turns[-1])
    with st.chat_message("assistant"):
        with st.spinner("Calling tools and writing the answer..."):
            try:
                turn = agent.ask(question)
            except Exception as e:
                st.error(f"Request failed: {type(e).__name__}: {e}")
                st.stop()
        st.markdown(turn.text)
        calls = [{"name": c.name, "input": c.input, "result": c.result} for c in turn.tool_calls]
        if calls:
            with st.expander(f"Data & assumptions ({len(calls)} tool call(s))"):
                for c in calls:
                    st.markdown(f"**{c['name']}** `{json.dumps(c['input'])}`")
                    st.json(c["result"], expanded=False)
        st.caption(f"tokens in/out: {turn.usage.get('input_tokens')}/{turn.usage.get('output_tokens')} · model {agent.model}")
    st.session_state.turns.append({"role": "assistant", "text": turn.text, "tool_calls": calls})
    if speak:
        speak_js(to_speech(turn.text))
