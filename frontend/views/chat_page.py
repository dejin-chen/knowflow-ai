import streamlit as st

from services.api_client import ApiClientError, BackendApiClient


def render_chat_page(
    client: BackendApiClient,
    selected_knowledge_base: dict,
) -> None:
    st.header("智能问答")
    st.caption(f"当前知识库：{selected_knowledge_base['name']}")

    try:
        documents = client.list_documents(selected_knowledge_base["id"])
    except ApiClientError as error:
        st.error(error)
        return

    if not any(document["status"] == "indexed" for document in documents):
        st.warning("当前知识库没有已建立向量索引的文档。")
        return

    _render_cache_status(client, selected_knowledge_base["id"])

    try:
        conversations = client.list_conversations(selected_knowledge_base["id"])
    except ApiClientError as error:
        st.error(error)
        return

    _render_conversation_selector(client, conversations)

    if st.button("新建会话", icon=":material/add_comment:"):
        st.session_state.current_conversation_id = None
        st.session_state.chat_messages = []
        st.rerun()

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_retrieval_details(message)
                _render_model_usage(message)
                _render_feedback_controls(client, message)

    question = st.chat_input("输入你的问题")
    if not question:
        return

    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("正在判断任务并生成回答..."):
            try:
                result = client.chat(
                    knowledge_base_id=selected_knowledge_base["id"],
                    question=question,
                    conversation_id=st.session_state.current_conversation_id,
                )
            except ApiClientError as error:
                st.session_state.chat_messages.pop()
                st.error(error)
                return

        st.markdown(result["answer"])
        assistant_message = {
            "role": "assistant",
            "assistant_message_id": result["assistant_message_id"],
            "content": result["answer"],
            "citations": result["citations"],
            "retrieved_chunk_count": result["retrieved_chunk_count"],
            "insufficient_evidence": result["insufficient_evidence"],
            "intent": result["intent"],
            "execution_steps": result["execution_steps"],
            "model_usages": result["model_usages"],
            "cache_hit": result["cache_hit"],
            "feedback": None,
        }
        _render_retrieval_details(assistant_message)
        _render_model_usage(assistant_message)
        _render_feedback_controls(client, assistant_message)
        st.session_state.current_conversation_id = result["conversation_id"]
        st.session_state.chat_messages.append(assistant_message)


def _render_conversation_selector(
    client: BackendApiClient,
    conversations: list[dict],
) -> None:
    options = [None] + [conversation["id"] for conversation in conversations]
    current_conversation_id = st.session_state.current_conversation_id
    selected_index = options.index(current_conversation_id) if current_conversation_id in options else 0
    selected_conversation_id = st.selectbox(
        "会话历史",
        options=options,
        index=selected_index,
        format_func=lambda conversation_id: _format_conversation_option(
            conversation_id,
            conversations,
        ),
    )

    if (
        selected_conversation_id is not None
        and selected_conversation_id != current_conversation_id
    ):
        try:
            messages = client.list_conversation_messages(selected_conversation_id)
        except ApiClientError as error:
            st.error(error)
            return
        st.session_state.current_conversation_id = selected_conversation_id
        st.session_state.chat_messages = [
            {
                "role": message["role"],
                "assistant_message_id": message["id"] if message["role"] == "assistant" else None,
                "content": message["content"],
                "citations": message["citations"],
                "intent": message.get("intent"),
                "execution_steps": message.get("execution_steps", []),
                "model_usages": message.get("model_usages", []),
                "cache_hit": False,
                "feedback": message.get("feedback"),
            }
            for message in messages
        ]
        st.rerun()


def _format_conversation_option(
    conversation_id: int | None,
    conversations: list[dict],
) -> str:
    if conversation_id is None:
        return "选择历史会话"
    conversation = next(item for item in conversations if item["id"] == conversation_id)
    return conversation["title"] or f"会话 {conversation_id}"


def _render_retrieval_details(message: dict) -> None:
    execution_steps = message.get("execution_steps", [])
    if execution_steps:
        with st.expander("系统执行步骤"):
            for step in execution_steps:
                st.markdown(f"{step['step_order']}. **{step['name']}**")
                st.caption(f"工具：{step['tool_name']}；{step['detail']}")

    if message.get("intent") == "clarification":
        st.caption("系统需要补充信息后才能继续执行。")
        return

    if message.get("insufficient_evidence"):
        st.caption("系统判断：知识库资料不足")
        return

    citations = message.get("citations", [])
    if citations:
        with st.expander("引用来源"):
            for citation in citations:
                st.markdown(f"**[{citation['reference_id']}] {citation['filename']}**")
                st.write(citation["content"])
                st.caption(_format_citation_caption(citation))

    if "retrieved_chunk_count" not in message:
        return

    chunk_count = message.get("retrieved_chunk_count", 0)
    if message.get("intent") in {"document_summary", "document_comparison"}:
        st.caption(f"使用 {chunk_count} 个文档片段")
    else:
        st.caption(f"命中 {chunk_count} 个检索片段")


def _render_model_usage(message: dict) -> None:
    if message.get("cache_hit"):
        st.caption("已命中高频回答缓存，本次未调用 Embedding 和聊天模型。")
        return

    model_usages = message.get("model_usages", [])
    if not model_usages:
        return

    with st.expander("模型用量"):
        for usage in model_usages:
            st.caption(
                f"{usage['model_name']}；输入 {usage['prompt_tokens']} Token；"
                f"输出 {usage['completion_tokens']} Token；"
                f"总计 {usage['total_tokens']} Token"
            )


def _render_cache_status(client: BackendApiClient, knowledge_base_id: int) -> None:
    try:
        stats = client.get_rag_cache_stats(knowledge_base_id)
    except ApiClientError as error:
        st.warning(f"缓存统计暂不可用：{error}")
        return

    with st.expander("回答缓存"):
        entry_column, hit_column, token_column = st.columns(3)
        entry_column.metric("有效缓存", stats["entry_count"])
        hit_column.metric("累计命中", stats["hit_count"])
        token_column.metric(
            "估算节省聊天 Token",
            stats["estimated_chat_tokens_saved"],
        )
        st.caption(
            f"有效期：{stats['ttl_seconds']} 秒；"
            f"当前知识库上限：{stats['max_entries_per_kb']} 条；"
            f"全局上限：{stats['max_entries']} 条"
        )
        if st.button(
            "清空回答缓存",
            icon=":material/delete_sweep:",
            disabled=stats["entry_count"] == 0,
        ):
            try:
                result = client.clear_rag_answer_cache(knowledge_base_id)
            except ApiClientError as error:
                st.error(error)
                return
            st.success(f"已清理 {result['deleted_entry_count']} 条缓存。")
            st.rerun()


def _render_feedback_controls(client: BackendApiClient, message: dict) -> None:
    assistant_message_id = message.get("assistant_message_id")
    if assistant_message_id is None:
        return

    feedback = message.get("feedback")
    if feedback:
        feedback_label = {
            "helpful": "已反馈：有帮助",
            "unhelpful": "已反馈：无帮助",
        }.get(feedback["feedback_type"], "已提交反馈")
        st.caption(feedback_label)
        return

    helpful_column, unhelpful_column = st.columns(2)
    if helpful_column.button(
        "有帮助",
        icon=":material/thumb_up:",
        key=f"feedback_helpful_{assistant_message_id}",
    ):
        _submit_feedback(client, message, "helpful")
    if unhelpful_column.button(
        "无帮助",
        icon=":material/thumb_down:",
        key=f"feedback_unhelpful_{assistant_message_id}",
    ):
        _submit_feedback(client, message, "unhelpful")


def _submit_feedback(
    client: BackendApiClient,
    message: dict,
    feedback_type: str,
) -> None:
    try:
        result = client.submit_answer_feedback(
            message["assistant_message_id"],
            feedback_type,
        )
    except ApiClientError as error:
        st.error(error)
        return

    message["feedback"] = result["feedback"]
    st.rerun()


def _format_citation_caption(citation: dict) -> str:
    if citation.get("distance") is None:
        return f"文档片段 {citation['chunk_index']}"
    return f"检索片段 {citation['chunk_index']}；距离 {citation['distance']:.3f}"
