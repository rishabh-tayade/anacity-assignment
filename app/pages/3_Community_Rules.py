import streamlit as st

from ui.runtime import get_container
from ui.sidebar import community_picker

from moveflow.domain.enums import RequestType

st.set_page_config(page_title="Community rules", page_icon=":material/tune:", layout="wide")

container = get_container()
config = community_picker(container)

st.title(f"{config.name} configuration")
st.caption(
    f"Loaded from `communities/{config.id.replace('-', '_')}.yaml`. "
    "Onboarding a new community means adding a file like this; no code changes."
)

autonomy = config.autonomy
with st.container(border=True):
    st.markdown("#### Agent autonomy")
    if autonomy.auto_approve:
        types = ", ".join(t.label for t in autonomy.request_types)
        occupancy = ", ".join(autonomy.occupancy)
        st.write(f"The agent may **auto-approve** {types} requests from **{occupancy}** residents "
                 "when every rule check passes. Everything else goes to the admin desk.")
    else:
        st.write("The agent **never approves on its own**. It guides residents and recommends; admins decide.")

rules_col, slots_col = st.columns([3, 2])
with rules_col:
    st.markdown("#### Rules")
    st.dataframe(
        [
            {"Rule": title, "What it means": description, "If broken": severity}
            for title, description, severity in container.compliance.describe_rules(config.id)
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption("*blocker*: the resident must fix it before submitting. *warning*: the admin decides.")
with slots_col:
    st.markdown("#### Move slots")
    st.dataframe(
        [{"Slot": slot.label, "Moves per slot": slot.capacity} for slot in config.time_slots],
        hide_index=True,
        width="stretch",
    )

for request_type in RequestType:
    st.markdown(f"#### {request_type.label}")
    fields_col, docs_col = st.columns(2)
    with fields_col:
        st.markdown("**What the agent asks**")
        st.dataframe(
            [
                {
                    "Field": spec.label,
                    "Type": spec.kind,
                    "Required": spec.required,
                    "Source": "profile" if spec.from_profile else "conversation",
                }
                for spec in config.fields_for(request_type)
            ],
            hide_index=True,
            width="stretch",
        )
    with docs_col:
        st.markdown("**Documents**")
        docs = [doc for doc in config.documents if request_type in doc.applies_to]
        if docs:
            st.dataframe(
                [{"Document": doc.label, "Needed from": ", ".join(doc.occupancy)} for doc in docs],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("None")

if config.faqs:
    st.markdown("#### FAQs the agent can answer")
    for faq in config.faqs:
        with st.expander(faq.question):
            st.write(faq.answer)
