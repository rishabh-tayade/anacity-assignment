"""Small rendering helpers reused by the resident and admin pages."""

import streamlit as st

from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import Actor, RequestStatus
from moveflow.domain.models import MoveRequest
from moveflow.formatting import format_answer
from moveflow.policies.base import CheckResult

STATUS_COLOURS = {
    RequestStatus.DRAFT: "gray",
    RequestStatus.SUBMITTED: "blue",
    RequestStatus.UNDER_REVIEW: "blue",
    RequestStatus.NEEDS_INFO: "orange",
    RequestStatus.APPROVED: "green",
    RequestStatus.REJECTED: "red",
    RequestStatus.COMPLETED: "violet",
    RequestStatus.CANCELLED: "gray",
}

ACTOR_LABELS = {
    Actor.RESIDENT: "Resident",
    Actor.ADMIN: "Admin",
    Actor.AGENT: "Agent",
    Actor.SYSTEM: "System",
}


def status_badge(status: RequestStatus) -> None:
    st.badge(status.label, color=STATUS_COLOURS[status])


def request_title(request: MoveRequest) -> str:
    when = request.move_date.strftime("%d %b") if request.move_date else "-"
    return f"{request.id} · {request.request_type.label} · {request.unit or '-'} · {when}"


def answers_table(request: MoveRequest, config: CommunityConfig) -> None:
    rows = [
        f"| {spec.label} | {format_answer(config, spec.key, request.answers.get(spec.key))} |"
        for spec in config.fields_for(request.request_type)
        if spec.key in request.answers
    ]
    st.markdown("| Field | Value |\n|---|---|\n" + "\n".join(rows))


def documents_list(request: MoveRequest, config: CommunityConfig) -> None:
    required = config.documents_for(request.request_type, request.occupancy)
    uploaded = request.uploaded_doc_types
    if not required and not uploaded:
        st.caption("No documents needed.")
        return
    for doc in required:
        icon = ":material/check_circle:" if doc.doc_type in uploaded else ":material/radio_button_unchecked:"
        st.markdown(f"{icon} {doc.label}")
    for doc_type in uploaded - {doc.doc_type for doc in required}:
        st.markdown(f":material/attach_file: {config.document_label(doc_type)}")


def timeline(request: MoveRequest) -> None:
    for event in request.timeline:
        note = f" - {event.note}" if event.note else ""
        st.markdown(f"`{event.at:%d %b %H:%M}` **{ACTOR_LABELS[event.actor]}**: {event.action}{note}")


def messages(request: MoveRequest) -> None:
    if not request.messages:
        st.caption("No messages yet.")
        return
    for message in request.messages:
        role = "user" if message.sender is Actor.RESIDENT else "assistant"
        with st.chat_message(role):
            st.caption(f"{ACTOR_LABELS[message.sender]} · {message.at:%d %b %H:%M}")
            st.write(message.text)


def check_list(checks: list[CheckResult]) -> None:
    for check in checks:
        if check.passed:
            icon = ":green[:material/check_circle:]"
        elif check.is_blocking:
            icon = ":red[:material/block:]"
        else:
            icon = ":orange[:material/warning:]"
        st.markdown(f"{icon} **{check.title}** - {check.message}")
