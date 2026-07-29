from app.schemas.agent import AgentIntent, AgentRouteDecision, AvailableDocument


class AgentRouterService:
    """轻量 Agent Router：根据问题类型选择一个受控工具。

    第一版使用显式规则，便于观察和测试。后续可将 ``route`` 内部替换为
    LLM 分类，但其输出仍必须被转换为 AgentRouteDecision，工具调用层无需改变。
    """

    summary_keywords = ("总结", "概括", "摘要", "梳理")
    comparison_keywords = ("比较", "对比", "区别", "差异")

    def route(
        self,
        question: str,
        available_documents: list[AvailableDocument],
    ) -> AgentRouteDecision:
        normalized_question = question.strip().lower()
        matched_documents = self._match_documents(
            normalized_question,
            available_documents,
        )

        if self._contains_any(normalized_question, self.comparison_keywords):
            return self._route_comparison(matched_documents)

        if self._contains_any(normalized_question, self.summary_keywords):
            return self._route_summary(matched_documents)

        return AgentRouteDecision(
            intent=AgentIntent.KNOWLEDGE_QA,
            tool_name="search_knowledge_base",
        )

    @staticmethod
    def _contains_any(question: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in question for keyword in keywords)

    @staticmethod
    def _match_documents(
        question: str,
        available_documents: list[AvailableDocument],
    ) -> list[AvailableDocument]:
        """按文件主名匹配，而非把文件全文交给 Router。

        例如文件 ``员工手册.md`` 的主名是“员工手册”。Router 只需要知道
        文档清单来确定工具参数；真正正文仍由工具从 Chunk 表中读取。
        """
        return [
            document
            for document in available_documents
            if document.filename.rsplit(".", maxsplit=1)[0].lower() in question
        ]

    @staticmethod
    def _route_summary(
        matched_documents: list[AvailableDocument],
    ) -> AgentRouteDecision:
        if len(matched_documents) == 1:
            return AgentRouteDecision(
                intent=AgentIntent.DOCUMENT_SUMMARY,
                tool_name="summarize_document",
                document_ids=[matched_documents[0].id],
            )

        return AgentRouteDecision(
            intent=AgentIntent.CLARIFICATION,
            tool_name="ask_clarifying_question",
            message="请说明要总结哪一份文档。",
        )

    @staticmethod
    def _route_comparison(
        matched_documents: list[AvailableDocument],
    ) -> AgentRouteDecision:
        if len(matched_documents) >= 2:
            return AgentRouteDecision(
                intent=AgentIntent.DOCUMENT_COMPARISON,
                tool_name="compare_documents",
                document_ids=[document.id for document in matched_documents],
            )

        return AgentRouteDecision(
            intent=AgentIntent.CLARIFICATION,
            tool_name="ask_clarifying_question",
            message="请说明需要比较的两份文档。",
        )
