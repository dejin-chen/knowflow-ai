from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSource:
    reference_id: int
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    content: str
    # 文档总结、对比并不经过相似度检索，因此 distance 可以为空。
    distance: float | None


@dataclass(frozen=True)
class RagPrompt:
    system_message: str
    user_message: str


class RagPromptService:
    """构造带资料边界和引用编号的 Prompt。"""

    qa_system_message = """你是 KnowFlow AI 企业知识库助手。请严格依据参考资料回答问题，不要把资料外的常识当作事实补充。
如果参考资料不足以直接回答问题，请明确回答“知识库中没有足够依据”。回答中的事实结论应使用 [编号] 标注对应参考资料。"""

    def build(self, question: str, sources: list[PromptSource]) -> RagPrompt:
        return RagPrompt(
            system_message=self.qa_system_message,
            user_message=(
                "请使用以下参考资料回答用户问题。\n\n"
                f"{self._build_source_blocks(sources)}\n\n"
                f"用户问题：{question}"
            ),
        )

    def build_document_summary(
        self,
        filename: str,
        sources: list[PromptSource],
    ) -> RagPrompt:
        return RagPrompt(
            system_message=(
                "你是 KnowFlow AI 企业知识库助手。请仅根据给出的文档片段，"
                "用清晰的要点总结指定文档；每项事实结论都要标记对应的 [编号]。"
                "若片段不足，请明确说明。"
            ),
            user_message=(
                f"请总结文档《{filename}》。\n\n"
                f"{self._build_source_blocks(sources)}"
            ),
        )

    def build_document_comparison(
        self,
        filenames: list[str],
        sources: list[PromptSource],
    ) -> RagPrompt:
        return RagPrompt(
            system_message=(
                "你是 KnowFlow AI 企业知识库助手。请仅根据给出的文档片段，"
                "比较不同文档的共同点和差异。不要补充片段之外的事实；"
                "每个事实结论都要标记对应的 [编号]。"
            ),
            user_message=(
                f"请比较以下文档：{'、'.join(filenames)}。\n\n"
                f"{self._build_source_blocks(sources)}"
            ),
        )

    def build_document_faq(
        self,
        filename: str,
        summary: str,
        sources: list[PromptSource],
        faq_count: int,
    ) -> RagPrompt:
        return RagPrompt(
            system_message=(
                "你是 KnowFlow AI 企业知识库助手。仅根据给出的文档摘要与参考资料，"
                "生成常见问题。必须只输出合法 JSON 数组，不能使用 Markdown 代码块或额外说明。"
                "数组必须恰好包含指定数量的对象；每个对象有 question、answer、reference_ids 三个字段。"
                "reference_ids 必须是实际存在的参考资料编号数组。"
            ),
            user_message=(
                f"为文档《{filename}》生成恰好 {faq_count} 条常见问答。\n\n"
                f"文档摘要：\n{summary}\n\n"
                f"{self._build_source_blocks(sources)}"
            ),
        )

    @staticmethod
    def _build_source_blocks(sources: list[PromptSource]) -> str:
        return "\n\n".join(
            (
                f"参考资料 [{source.reference_id}]\n"
                f"来源文件：{source.filename}\n"
                f"Chunk：{source.chunk_index}\n"
                f"内容：{source.content}"
            )
            for source in sources
        )
