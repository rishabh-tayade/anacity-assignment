import streamlit as st

from ui import widgets
from ui.runtime import get_container
from ui.sidebar import community_picker

from moveflow.agents.review.admin_copilot import ReviewBrief
from moveflow.agents.review.recommender import Decision
from moveflow.agents.review.triage import prioritise
from moveflow.container import Container
from moveflow.domain.enums import Actor, RequestStatus
from moveflow.domain.models import MoveRequest
from moveflow.domain.state_machine import AWAITING_ADMIN

st.set_page_config(page_title="Admin desk", page_icon=":material/admin_panel_settings:", layout="wide")

container: Container = get_container()
config = community_picker(container)

DECISION_STYLE = {
    Decision.APPROVE: st.success,
    Decision.REQUEST_INFO: st.warning,
    Decision.REJECT: st.error,
    Decision.WAIT: st.info,
}
ACTIONABLE = [Decision.APPROVE, Decision.REQUEST_INFO, Decision.REJECT]


def cached_brief(request: MoveRequest) -> ReviewBrief:
    """Briefs can involve a model call, so keep one per request version."""
    key = f"brief:{request.id}:{request.updated_at.isoformat()}"
    if key not in st.session_state:
        with st.spinner("Preparing the review brief..."):
            st.session_state[key] = container.copilot.brief(request)
    return st.session_state[key]


def render_metrics(requests: list[MoveRequest]) -> None:
    waiting = sum(1 for r in requests if r.status in AWAITING_ADMIN)
    needs_info = sum(1 for r in requests if r.status is RequestStatus.NEEDS_INFO)
    approved = [r for r in requests if r.status is RequestStatus.APPROVED]
    auto = sum(1 for r in approved if any(e.actor is Actor.AGENT for e in r.timeline))
    cols = st.columns(4)
    cols[0].metric("Waiting for review", waiting)
    cols[1].metric("Waiting on residents", needs_info)
    cols[2].metric("Approved, upcoming", len(approved))
    cols[3].metric("Auto-approved by agent", auto)


def render_queue(requests: list[MoveRequest]) -> MoveRequest | None:
    statuses = st.pills(
        "Show",
        list(RequestStatus)[1:],
        selection_mode="multi",
        default=[RequestStatus.UNDER_REVIEW, RequestStatus.NEEDS_INFO, RequestStatus.APPROVED],
        format_func=lambda status: status.label,
    )
    queue = prioritise([r for r in requests if r.status in statuses], container.today())
    if not queue:
        st.info("Nothing in the queue for these filters.")
        return None

    rows = [
        {
            "Request": r.id,
            "Type": r.request_type.label,
            "Unit": r.unit,
            "Resident": r.resident_name,
            "Move date": r.move_date,
            "Status": r.status.label,
        }
        for r in queue
    ]
    selection = st.dataframe(rows, hide_index=True, on_select="rerun", selection_mode="single-row", width="stretch")
    selected_rows = selection.selection.rows
    return queue[selected_rows[0]] if selected_rows else queue[0]


def render_brief(request: MoveRequest, brief: ReviewBrief) -> None:
    st.markdown("#### Copilot brief")
    st.write(brief.summary)
    st.caption(f"Written by: {brief.summary_source}")
    if brief.days_to_move is not None and 0 <= brief.days_to_move <= 2 and request.status in AWAITING_ADMIN:
        st.error(f"Move is in {brief.days_to_move} day(s). Decide soon.", icon=":material/schedule:")

    if brief.recommendation:
        rec = brief.recommendation
        show = DECISION_STYLE[rec.decision]
        show(f"**Recommended: {rec.decision.label}** ({rec.confidence} confidence)\n\n"
             + "\n".join(f"- {reason}" for reason in rec.reasons))

    st.markdown("#### Rule checks")
    widgets.check_list(brief.checks)
    if brief.alternatives:
        st.caption("Free slots: " + "; ".join(option.describe() for option in brief.alternatives))


def render_actions(request: MoveRequest, brief: ReviewBrief) -> None:
    if request.status is RequestStatus.APPROVED:
        complete, cancel = st.columns(2)
        if complete.button("Mark move as completed", icon=":material/task_alt:"):
            container.requests.complete(request.id)
            st.rerun()
        if cancel.button("Cancel this move", icon=":material/close:"):
            container.requests.cancel(request.id, "Cancelled by the admin desk", actor=Actor.ADMIN)
            st.rerun()
        return
    if request.status not in AWAITING_ADMIN:
        return

    st.markdown("#### Decide")
    recommended = brief.recommendation.decision if brief.recommendation else Decision.APPROVE
    decision = st.segmented_control(
        "Action",
        ACTIONABLE,
        default=recommended if recommended in ACTIONABLE else Decision.APPROVE,
        format_func=lambda d: d.label,
        key=f"decision:{request.id}",
    ) or recommended

    draft_key = f"draft:{request.id}:{decision}:{request.updated_at.isoformat()}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = container.copilot.draft_message(request, brief, decision)
    message = st.text_area("Message to the resident (drafted by the copilot, edit freely)", key=draft_key, height=180)

    if st.button(f"Send: {decision.label}", type="primary"):
        if decision is Decision.APPROVE:
            container.requests.approve(request.id, message)
        elif decision is Decision.REQUEST_INFO:
            container.requests.request_info(request.id, message)
        else:
            container.requests.reject(request.id, message)
        st.toast(f"{request.id}: {decision.label}")
        st.rerun()


def render_details(request: MoveRequest) -> None:
    details, history = st.tabs(["Details", "Messages & timeline"])
    with details:
        widgets.answers_table(request, config)
        st.markdown("**Documents**")
        widgets.documents_list(request, config)
    with history:
        widgets.messages(request)
        st.divider()
        widgets.timeline(request)


st.title(f"{config.name} admin desk")
all_requests = container.repository.list(config.id)
render_metrics(all_requests)
selected = render_queue(all_requests)

if selected:
    st.divider()
    header, badge = st.columns([5, 1])
    header.subheader(widgets.request_title(selected))
    with badge:
        widgets.status_badge(selected.status)

    brief = cached_brief(selected)
    left, right = st.columns([3, 2])
    with left:
        render_brief(selected, brief)
        render_actions(selected, brief)
    with right:
        render_details(selected)
