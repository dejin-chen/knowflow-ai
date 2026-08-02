import streamlit as st

from services.api_client import ApiClientError, BackendApiClient


def render_knowledge_base_page(
    client: BackendApiClient,
    knowledge_bases: list[dict],
    selected_knowledge_base: dict | None,
) -> None:
    st.header("知识库管理")

    with st.form("create_knowledge_base_form", clear_on_submit=True):
        name = st.text_input("知识库名称", placeholder="例如：员工制度库")
        description = st.text_area("知识库说明", placeholder="说明资料范围，可选")
        submitted = st.form_submit_button("创建知识库")

    if submitted:
        try:
            knowledge_base = client.create_knowledge_base(name, description)
            st.session_state.pending_selected_knowledge_base_id = knowledge_base["id"]
            st.toast("知识库创建成功")
            st.rerun()
        except ApiClientError as error:
            st.error(error)

    st.subheader("知识库列表")
    if not knowledge_bases:
        st.info("还没有知识库。")
        return

    st.dataframe(
        [
            {
                "ID": item["id"],
                "名称": item["name"],
                "说明": item["description"] or "",
                "创建时间": item["created_at"],
            }
            for item in knowledge_bases
        ],
        hide_index=True,
        width="stretch",
    )

    if selected_knowledge_base is None:
        return

    st.subheader(f"上传文档：{selected_knowledge_base['name']}")
    uploaded_file = st.file_uploader(
        "选择 TXT、Markdown 或 PDF 文档",
        type=["txt", "md", "markdown", "pdf"],
    )
    if st.button("上传文档", disabled=uploaded_file is None):
        try:
            client.upload_document(selected_knowledge_base["id"], uploaded_file)
            st.toast("文档上传成功")
            st.rerun()
        except ApiClientError as error:
            st.error(error)

    try:
        documents = client.list_documents(selected_knowledge_base["id"])
    except ApiClientError as error:
        st.error(error)
        return

    if documents:
        st.subheader("文档列表")
        st.dataframe(
            [
                {
                    "文件名": document["filename"],
                    "类型": document["file_type"],
                    "大小（字节）": document["file_size"],
                    "状态": document["status"],
                    "上传时间": document["created_at"],
                }
                for document in documents
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    delete_confirmed = st.checkbox(
        "我确认删除当前知识库及其关联数据",
        key=f"delete_confirmed_{selected_knowledge_base['id']}",
    )
    if st.button("删除当前知识库", disabled=not delete_confirmed):
        try:
            client.delete_knowledge_base(selected_knowledge_base["id"])
            st.session_state.pending_selected_knowledge_base_id = None
            st.toast("知识库已删除")
            st.rerun()
        except ApiClientError as error:
            st.error(error)
