import streamlit as st

from ui import widgets
from ui.runtime import get_container
from ui.sidebar import community_picker

from moveflow.agents.intake.conversation import IntakeSession
from moveflow.agents.intake.intake_agent import AgentReply, IntakeAgent
from moveflow.config.schema import CommunityConfig
from moveflow.container import Container
from moveflow.demo.seed import DEMO_RESIDENTS
from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest, UploadedDocument
from moveflow.domain.state_machine import is_final

st.set_page_config(page_title="Plan a move", page_icon=":material/person:", layout="wide")

container: Container = get_container()
config = community_picker(container)
agent = container.intake_agent(config.id)


def signed_in_resident(config: CommunityConfig) -> tuple[str, str]:
    """Stands in for the logged-in ANACITY user."""
    residents = DEMO_RESIDENTS.get(config.id, [])
    labels = [resident.name for resident in residents] + ["Someone else"]
    with st.sidebar:
        st.divider()
        index = st.selectbox("Signed in as", range(len(labels)), format_func=lambda i: labels[i])
        if index < len(residents):
            st.caption(residents[index].note)
            return residents[index].name, residents[index].phone
        return st.text_input("Your name", "Guest Resident"), st.text_input("Phone", "9800000000")


def session_key(phone: str) -> str:
    return f"intake:{config.id}:{phone}"


def load_session(name: str, phone: str) -> IntakeSession:
    key = session_key(phone)
    if key not in st.session_state:
        session = IntakeSession.start(config.id, {"resident_name": name, "phone": phone})
        agent.greet(session)
        st.session_state[key] = session
    return st.session_state[key]


def render_chat(agent: IntakeAgent, session: IntakeSession) -> None:
    history = st.container(height=560, border=True)
    for turn in session.turns:
        with history.chat_message("user" if turn.role == "resident" else "assistant"):
            st.markdown(turn.text)
    if prompt := st.chat_input("Describe your move, answer the agent or ask a question"):
        with st.spinner("Thinking..."):
            st.session_state["last_reply"] = agent.handle(session, prompt)
        st.rerun()


def render_draft(session: IntakeSession) -> None:
    st.markdown("#### Your request")
    if session.submitted_request_id:
        st.success(f"Submitted as **{session.submitted_request_id}**. Track it under *My requests*.")
    if session.request_type is None:
        st.caption("Nothing yet. Tell the agent what you're planning.")
        return
    st.markdown(f"**{session.request_type.label}**")
    draft = session.to_draft()
    widgets.answers_table(draft, config)


def render_documents(agent: IntakeAgent, session: IntakeSession) -> None:
    if session.request_type is None or session.submitted_request_id:
        return
    st.markdown("#### Documents")
    draft = session.to_draft()
    required = config.documents_for(draft.request_type, draft.occupancy)
    if draft.occupancy is None:
        st.caption("The agent will tell you what's needed once it knows whether you're an owner or a tenant.")
        return
    if not required:
        st.caption("No documents needed for this request.")
        return
    widgets.documents_list(draft, config)

    missing = [doc for doc in required if doc.doc_type not in draft.uploaded_doc_types] or required
    doc_type = st.selectbox(
        "Document", [doc.doc_type for doc in missing], format_func=config.document_label, key="doc_type"
    )
    upload_count = st.session_state.get("upload_count", 0)
    file = st.file_uploader("File", type=["pdf", "jpg", "jpeg", "png"], key=f"upload_{upload_count}")
    if st.button("Attach", disabled=file is None, icon=":material/upload:"):
        document = UploadedDocument(doc_type=doc_type, file_name=file.name)
        st.session_state["last_reply"] = agent.add_document(session, document)
        st.session_state["upload_count"] = upload_count + 1
        st.rerun()


def render_reasoning(reply: AgentReply | None) -> None:
    with st.expander("How the agent read your last message"):
        if reply is None:
            st.caption("Send a message to see what the agent understood and why it replied the way it did.")
            return
        if reply.extraction:
            st.markdown(f"**Understood by:** {reply.extraction.source} · **intent:** {reply.extraction.intent}")
            if reply.extraction.values:
                st.json(reply.extraction.values)
            for ambiguity in reply.extraction.ambiguities:
                st.markdown(f"Unclear: *{ambiguity.field}* - {ambiguity.question}")
        if reply.step:
            st.markdown(f"**Next step chosen:** `{reply.step.kind}`")
            widgets.check_list(reply.step.checks)


def render_my_requests(container: Container, phone: str) -> None:
    requests = container.repository.list_for_resident(config.id, phone)
    if not requests:
        st.info("You haven't raised any move requests in this community yet.")
        return
    for request in requests:
        render_request_card(container, request)


def render_request_card(container: Container, request: MoveRequest) -> None:
    with st.container(border=True):
        title, badge = st.columns([4, 1])
        title.markdown(f"**{widgets.request_title(request)}**")
        with badge:
            widgets.status_badge(request.status)
        if request.status is RequestStatus.NEEDS_INFO:
            st.warning("The admin desk needs something from you. See the messages below.")

        with st.expander("Details", expanded=request.status is RequestStatus.NEEDS_INFO):
            details, conversation = st.columns(2)
            with details:
                widgets.answers_table(request, config)
                st.markdown("**Documents**")
                widgets.documents_list(request, config)
                st.markdown("**Timeline**")
                widgets.timeline(request)
            with conversation:
                st.markdown("**Messages**")
                widgets.messages(request)
                if request.status is RequestStatus.APPROVED:
                    st.markdown("**Move-day checklist**")
                    for item in config.move_day_checklist.get(request.request_type, []):
                        st.checkbox(item, key=f"check:{request.id}:{item}")

            if request.status is RequestStatus.NEEDS_INFO:
                render_reply_form(container, request)
            if not is_final(request.status):
                if st.button("Cancel this request", key=f"cancel:{request.id}", icon=":material/close:"):
                    container.requests.cancel(request.id, "Cancelled by resident")
                    st.rerun()


def render_reply_form(container: Container, request: MoveRequest) -> None:
    with st.form(f"reply:{request.id}", clear_on_submit=True):
        text = st.text_area("Reply to the admin desk")
        doc_options = [doc.doc_type for doc in config.documents_for(request.request_type, request.occupancy)]
        doc_type = st.selectbox(
            "Attach a document (optional)", ["", *doc_options],
            format_func=lambda value: config.document_label(value) if value else "-",
        )
        file = st.file_uploader("File", type=["pdf", "jpg", "jpeg", "png"])
        if st.form_submit_button("Send reply"):
            documents = [UploadedDocument(doc_type=doc_type, file_name=file.name)] if doc_type and file else []
            container.requests.reply_to_admin(request.id, text, documents)
            st.rerun()


name, phone = signed_in_resident(config)
session = load_session(name, phone)

st.title(f"Plan a move at {config.name}")
plan_tab, requests_tab = st.tabs(["Plan a move", "My requests"])

with plan_tab:
    chat_column, side_column = st.columns([3, 2])
    with chat_column:
        render_chat(agent, session)
    with side_column:
        render_draft(session)
        render_documents(agent, session)
        render_reasoning(st.session_state.get("last_reply"))
        if st.button("Start a new request", icon=":material/restart_alt:"):
            del st.session_state[session_key(phone)]
            st.session_state.pop("last_reply", None)
            st.rerun()

with requests_tab:
    render_my_requests(container, phone)
