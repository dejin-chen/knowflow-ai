import streamlit as st

from core.config import settings
from services.api_client import ApiClientError, BackendApiClient
from views.chat_page import render_chat_page
from views.document_processing_page import render_document_processing_page
from views.knowledge_base_page import render_knowledge_base_page


NO_PENDING_SELECTION = object()


st.set_page_config(
    page_title="KnowFlow AI",
    page_icon=":material/auto_stories:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def reset_chat_state() -> None:
    st.session_state.current_conversation_id = None
    st.session_state.chat_messages = []


def initialize_state() -> None:
    st.session_state.setdefault("selected_knowledge_base_id", None)
    st.session_state.setdefault("current_conversation_id", None)
    st.session_state.setdefault("chat_messages", [])

    # 不能在 selectbox 创建后直接修改它绑定的 state。页面重新运行时，
    # 先消费上一轮操作留下的待选知识库，再创建侧边栏控件。
    pending_selection = st.session_state.pop(
        "pending_selected_knowledge_base_id",
        NO_PENDING_SELECTION,
    )
    if pending_selection is not NO_PENDING_SELECTION:
        st.session_state.selected_knowledge_base_id = pending_selection
        reset_chat_state()


def render_sidebar(knowledge_bases: list[dict]) -> tuple[str, dict | None]:
    st.sidebar.title("KnowFlow AI")
    st.sidebar.caption("企业知识库 RAG 问答平台")

    if not knowledge_bases:
        st.sidebar.info("请先创建知识库。")
        return st.sidebar.radio("功能", ["知识库管理"]), None

    knowledge_base_ids = [item["id"] for item in knowledge_bases]
    if st.session_state.selected_knowledge_base_id not in knowledge_base_ids:
        st.session_state.selected_knowledge_base_id = knowledge_base_ids[0]
        reset_chat_state()

    previous_id = st.session_state.selected_knowledge_base_id
    selected_id = st.sidebar.selectbox(
        "当前知识库",
        options=knowledge_base_ids,
        format_func=lambda item_id: next(
            item["name"] for item in knowledge_bases if item["id"] == item_id
        ),
        key="selected_knowledge_base_id",
    )
    if selected_id != previous_id:
        reset_chat_state()

    page = st.sidebar.radio(
        "功能",
        ["知识库管理", "文档处理", "智能问答"],
    )
    selected_knowledge_base = next(
        item for item in knowledge_bases if item["id"] == selected_id
    )
    return page, selected_knowledge_base


def main() -> None:
    initialize_state()
    client = BackendApiClient(settings.api_base_url)

    try:
        knowledge_bases = client.list_knowledge_bases()
    except ApiClientError as error:
        st.error(f"无法连接后端服务：{error}")
        st.stop()

    page, selected_knowledge_base = render_sidebar(knowledge_bases)
    if page == "知识库管理":
        render_knowledge_base_page(client, knowledge_bases, selected_knowledge_base)
    elif page == "文档处理" and selected_knowledge_base:
        render_document_processing_page(client, selected_knowledge_base)
    elif page == "智能问答" and selected_knowledge_base:
        render_chat_page(client, selected_knowledge_base)


if __name__ == "__main__":
    main()
