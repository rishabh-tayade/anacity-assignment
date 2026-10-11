import streamlit as st

from moveflow.config.schema import CommunityConfig
from moveflow.container import Container

COMMUNITY_KEY = "community_id"


def community_picker(container: Container) -> CommunityConfig:
    """Community selector shared by all pages; the choice survives page switches."""
    communities = container.catalog.all()
    ids = [config.id for config in communities]
    current = st.session_state.get(COMMUNITY_KEY, ids[0])

    with st.sidebar:
        selected = st.selectbox(
            "Community",
            ids,
            index=ids.index(current) if current in ids else 0,
            format_func=lambda cid: container.catalog.get(cid).name,
        )
        st.session_state[COMMUNITY_KEY] = selected
        _ai_mode(container)
    return container.catalog.get(selected)


def _ai_mode(container: Container) -> None:
    model = container.ai.model_name
    if model:
        st.caption(f"AI: **{model}** (rules take over if a call fails)")
    else:
        st.caption("AI: **rule-based mode**. Set `ANTHROPIC_API_KEY` to use Claude.")
