import streamlit as st

from services.api_client import ApiClientError, BackendApiClient


STATUS_LABELS = {
    "uploaded": "已上传",
    "chunked": "已切分",
    "indexed": "已就绪",
}


def render_document_processing_page(
    client: BackendApiClient,
    selected_knowledge_base: dict,
) -> None:
    st.header("文档处理")
    st.caption(f"当前知识库：{selected_knowledge_base['name']}")

    try:
        documents = client.list_documents(selected_knowledge_base["id"])
    except ApiClientError as error:
        st.error(error)
        return

    if not documents:
        st.info("当前知识库还没有文档。")
        return

    for document in documents:
        _render_document_row(client, document)


def _render_document_row(client: BackendApiClient, document: dict) -> None:
    status = document["status"]
    status_label = STATUS_LABELS.get(status, status)
    name_column, status_column, process_column, summary_column = st.columns([4, 1, 2, 2])
    name_column.write(document["filename"])
    status_column.write(status_label)

    try:
        _render_process_action(client, document, process_column)
        _render_summary_action(client, document, summary_column)
        _render_faq_action(client, document, summary_column)
    except ApiClientError as error:
        st.error(f"{document['filename']}：{error}")

    _render_saved_summary(document)
    _render_saved_faqs(document)


def _render_process_action(
    client: BackendApiClient,
    document: dict,
    column,
) -> None:
    status = document["status"]
    if status == "uploaded":
        if column.button(
            "切分文档",
            icon=":material/content_cut:",
            key=f"chunk_{document['id']}",
        ):
            with st.spinner("正在解析并切分文档..."):
                result = client.process_document_chunks(document["id"])
            st.toast(f"已生成 {result['chunk_count']} 个检索片段")
            st.rerun()
    elif status == "chunked":
        if column.button(
            "建立索引",
            icon=":material/database:",
            key=f"index_{document['id']}",
        ):
            with st.spinner("正在生成 Embedding 并写入向量库..."):
                result = client.index_document(document["id"])
            st.toast(f"已建立 {result['indexed_chunk_count']} 个向量索引")
            st.rerun()
    elif status == "indexed":
        column.success("可问答")
    else:
        column.warning("状态未知")


def _render_summary_action(
    client: BackendApiClient,
    document: dict,
    column,
) -> None:
    if document["status"] not in {"chunked", "indexed"}:
        column.caption("完成切分后可生成摘要")
        return

    has_summary = document.get("summary") is not None
    button_label = "重新生成摘要" if has_summary else "生成摘要"
    if column.button(
        button_label,
        icon=":material/summarize:",
        key=f"summary_{document['id']}",
    ):
        with st.spinner("正在根据文档片段生成摘要..."):
            client.generate_document_summary(document["id"])
        st.toast("文档摘要已保存")
        st.rerun()


def _render_saved_summary(document: dict) -> None:
    summary = document.get("summary")
    if not summary:
        return

    with st.expander(f"摘要：{document['filename']}"):
        st.markdown(summary["content"])
        if summary["total_tokens"] is not None:
            st.caption(
                f"{summary['model_name']}；输入 {summary['prompt_tokens']} Token；"
                f"输出 {summary['completion_tokens']} Token；"
                f"总计 {summary['total_tokens']} Token"
            )
        if summary["citations"]:
            with st.expander("摘要引用来源"):
                for citation in summary["citations"]:
                    st.markdown(
                        f"**[{citation['reference_id']}] {citation['filename']}**"
                    )
                    st.write(citation["content"])


def _render_faq_action(
    client: BackendApiClient,
    document: dict,
    column,
) -> None:
    if document.get("summary") is None:
        return

    has_faqs = bool(document.get("faqs"))
    button_label = "重新生成 FAQ" if has_faqs else "生成 FAQ"
    if column.button(
        button_label,
        icon=":material/quiz:",
        key=f"faq_{document['id']}",
    ):
        with st.spinner("正在生成常见问答..."):
            client.generate_document_faqs(document["id"])
        st.toast("文档 FAQ 已保存")
        st.rerun()


def _render_saved_faqs(document: dict) -> None:
    faqs = document.get("faqs", [])
    if not faqs:
        return

    with st.expander(f"常见问答：{document['filename']}"):
        for faq in faqs:
            st.markdown(f"**问：{faq['question']}**")
            st.write(faq["answer"])
            reference_ids = [
                str(citation["reference_id"])
                for citation in faq["citations"]
            ]
            st.caption(f"引用来源：{', '.join(reference_ids)}")
