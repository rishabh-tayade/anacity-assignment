import streamlit as st

from ui.runtime import get_container
from ui.sidebar import community_picker

st.set_page_config(page_title="ANACITY Move Desk", page_icon=":material/local_shipping:", layout="wide")

container = get_container()
config = community_picker(container)

st.title("ANACITY Move Desk")
st.write(
    "An agentic workflow for move-ins and move-outs. Residents plan their move by chatting with an "
    "intake agent; the admin desk reviews requests with a copilot that checks every community rule "
    "and drafts the reply."
)

resident, admin, rules = st.columns(3)
with resident:
    with st.container(border=True):
        st.subheader(":material/person: Resident")
        st.write(
            "Describe your move in plain words. The agent fills in the form, checks the community rules "
            "as you go, suggests free slots, tells you which documents to upload and keeps you posted."
        )
        st.page_link("pages/1_Resident.py", label="Plan a move", icon=":material/arrow_forward:")
with admin:
    with st.container(border=True):
        st.subheader(":material/admin_panel_settings: Admin desk")
        st.write(
            "A prioritised queue. Each request comes with a short brief, the result of every rule check, "
            "a recommended action with reasons, and a drafted message to the resident."
        )
        st.page_link("pages/2_Admin.py", label="Open the queue", icon=":material/arrow_forward:")
with rules:
    with st.container(border=True):
        st.subheader(":material/tune: Community rules")
        st.write(
            "Every community has its own fields, slots, documents, rules and autonomy level, "
            "all read from a YAML file. Nothing community-specific is in code."
        )
        st.page_link("pages/3_Community_Rules.py", label="See the rules", icon=":material/arrow_forward:")

st.subheader("Try these")
st.markdown(
    """
1. **Green Meadows, resident Ananya:** *"I'm moving into flat 1204 this weekend as a tenant"*. The agent asks
   which tower and which day, explains that Sundays are blocked, offers free slots and asks for the tenant documents.
2. **Green Meadows, admin:** open Priya Nair's move-out. The copilot spots the pending dues and drafts a message
   asking her to clear them. Karan Malhotra's move-in is flagged because D-404 is still occupied.
3. **Skyline Towers, resident Kavita:** *"Moving out of T1-1203 on the 20th, first half, I'm the owner"*.
   The request passes every rule and Skyline allows auto-approval for owners, so the agent approves it right away.
4. **Green Meadows, resident Farhan:** answer the desk's question under *My requests*; the request goes back
   to the admin queue.
"""
)
