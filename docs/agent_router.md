# 受控 Agent Router

## 能力范围

基础 RAG 只处理“从知识库查资料并回答”的问题，但用户还可能提出：

- “总结员工手册”
- “比较员工手册和报销制度的差异”
- “请总结这份制度”（目标不明确）

这些问题不应该全部强行走同一条 RAG 问答链路。因此增加 Router，先识别意图，再选择一个工具。

## Router 与工具的职责

```text
用户问题
  -> AgentRouterService.route
  -> AgentRouteDecision（意图、工具名、目标文档 ID）
  -> 对应工具执行
  -> 回答、引用来源、执行步骤
```

第一版支持四种意图：

| 意图 | 工具 | 作用 |
| --- | --- | --- |
| `knowledge_qa` | `search_knowledge_base` | 调用已有 RAG 问答能力 |
| `document_summary` | `summarize_document` | 总结一份指定文档 |
| `document_comparison` | `compare_documents` | 对比两份或多份指定文档 |
| `clarification` | `ask_clarifying_question` | 文档目标不明确时请求补充 |

## 为什么先使用规则 Router

当前实现通过“总结”“比较”等关键词和文件名匹配生成结构化决策，行为稳定、便于单元测试，也便于研发与运维人员审计路由过程。

以后可把内部分类器替换为 LLM，但不要让 LLM 直接执行任意代码。LLM 的输出仍要校验为有限的 `AgentIntent` 与真实的文档 ID，然后才能调用工具。这就是“受控工具调用”的基本思想。

## 已接通的工具

- `search_knowledge_base`：复用 `RagChatService`，保留语义检索、RAG Prompt、引用来源和检索日志。
- `summarize_document`：从 SQLite 的 `document_chunks` 读取一份明确指定文档的片段，构造总结 Prompt。
- `compare_documents`：从 SQLite 的 `document_chunks` 读取两份或多份明确指定文档的片段，构造对比 Prompt。
- `ask_clarifying_question`：当用户说“总结这份制度”但没有明确文件名时，保存本轮会话消息并请求补充目标文档。

文档总结与对比不经过向量检索：因为用户已经明确目标文档，系统直接读取其 Chunk 即可。为避免超长文档一次占满模型上下文，`AGENT_TOOL_CONTEXT_CHARACTERS` 默认限制为 10000 个字符，可在 `.env` 中调整。

## 执行记录持久化

每次 Agent 返回助手消息后，系统会新增一条 `agent_runs` 记录，并新增多条 `agent_steps` 记录：

- `agent_runs`：关联知识库、会话、助手消息和最终识别出的意图。
- `agent_steps`：按顺序保存 Router 判断与工具执行的名称、工具名、状态和说明。

历史会话接口会按助手消息关联 `agent_runs`，因此重新打开会话时，页面也能恢复当时的“系统执行步骤”。

## 当前已接通的工具

`AgentChatService` 是聊天接口的编排层。目前已经接通：

- `search_knowledge_base`：复用 `RagChatService`，因此语义检索、RAG Prompt、引用来源和检索日志无需重写。
- `ask_clarifying_question`：当用户说“总结这份制度”但没有明确文件名时，保存本轮会话消息并要求用户补充目标文档。

聊天接口会在响应中返回 `execution_steps`。Streamlit 会将其显示为“系统执行步骤”，让使用者看到 Router 的判断和实际工具调用。下一步将实现 `summarize_document` 与 `compare_documents` 两个工具。
