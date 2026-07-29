from enum import Enum

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    """Router 能识别的有限意图集合。

    有限集合是轻量 Agent 的边界：Router 只能从已实现的工具中选择，
    不能临时编造一个系统不存在的工具。
    """

    KNOWLEDGE_QA = "knowledge_qa"
    DOCUMENT_SUMMARY = "document_summary"
    DOCUMENT_COMPARISON = "document_comparison"
    CLARIFICATION = "clarification"


class AvailableDocument(BaseModel):
    """供 Router 识别用户提到的文档，不包含文档正文。"""

    id: int
    filename: str


class AgentRouteDecision(BaseModel):
    """Router 的结构化输出，也是后续工具调用的输入。"""

    intent: AgentIntent
    tool_name: str
    document_ids: list[int] = Field(default_factory=list)
    message: str | None = None


class AgentExecutionStep(BaseModel):
    """一次 Agent 调用中可展示的步骤。"""

    step_order: int
    name: str
    tool_name: str
    status: str
    detail: str
