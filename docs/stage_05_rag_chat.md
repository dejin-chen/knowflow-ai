# 第五阶段：RAG 问答与引用溯源

## 阶段目标

本阶段将第四阶段的语义检索结果交给聊天模型，生成带真实引用来源的回答，并保存完整问答与检索记录。

```text
用户问题
  ↓
Chroma 语义检索 Top-K Chunks
  ↓
判断资料是否足够
  ↓
构造 RAG Prompt
  ↓
聊天模型生成回答
  ↓
回答 + 引用来源 + 会话消息 + 检索日志
```

## 新增三张表

### conversations

一条会话记录代表用户在某个知识库下的一次连续问答。

- `knowledge_base_id`：会话所属知识库
- `title`：首个问题的前 80 个字符
- `created_at` / `updated_at`：会话时间

### messages

保存用户问题和助手回答。

- `conversation_id`：所属会话
- `role`：`user` 或 `assistant`
- `content`：问题或回答正文
- `citations`：助手回答的结构化引用列表

### retrieval_logs

记录“这一次回答实际检索了什么”，用于排错和后续可观测性建设。

- `query`：用户问题
- `top_k`：检索数量
- `best_distance`：最佳命中距离
- `retrieved_chunks`：命中的 Chunk、来源和距离
- `user_message_id` / `assistant_message_id`：关联本次问答消息

## RAG Prompt

Prompt 由 `RagPromptService` 构造，包含四部分：

1. 角色：企业知识库助手。
2. 边界：只能依据参考资料回答。
3. 参考资料：按向量距离排序的 `[1]`、`[2]` 等 Chunk。
4. 用户问题：当前需要回答的问题。

资料编号是本次回答临时使用的 `reference_id`，不是数据库的 `chunk_id`。

## 资料不足策略

系统有两层判断：

- 没有检索结果，或最佳距离大于 `RETRIEVAL_DISTANCE_THRESHOLD`：后端直接返回“知识库中没有足够依据”，不调用 LLM。
- 有相关候选资料：Prompt 要求 LLM 如果资料无法直接支持结论，也必须明确说明资料不足。

这样减少了模型用常识编造企业规则的风险。

## 接口

```text
POST /api/knowledge-bases/{knowledge_base_id}/chat
```

请求示例：

```json
{
  "question": "病假需要提交什么材料？",
  "conversation_id": null,
  "top_k": 3
}
```

响应包含：

- `answer`：模型回答或资料不足提示
- `citations`：后端生成的真实来源列表
- `retrieved_chunk_count`：实际召回的 Chunk 数量
- `insufficient_evidence`：是否资料不足

## 本阶段学到了什么

- 第四阶段负责找资料，第五阶段负责用资料约束模型回答。
- LLM 可以生成自然语言，但引用来源必须由后端基于检索结果保存和返回。
- 检索相关不等于资料足够回答，需要后端阈值和 Prompt 规则双重控制。
- 会话、消息和检索日志让每次回答都可追踪、可复盘。

## 简历写法

> 实现企业知识库 RAG 问答链路：基于语义检索结果构造受资料边界约束的 Prompt，调用 OpenAI 兼容聊天模型生成回答；设计会话、消息与检索日志表，保存结构化引用来源，并通过距离阈值与资料不足策略降低模型幻觉风险。

## 面试可能追问

1. 为什么引用不只由 LLM 生成？

回答思路：LLM 可能遗漏、写错或编造引用编号。系统由后端根据真实检索结果建立 `reference_id -> chunk_id -> document` 映射，前端展示的数据才可追溯。

2. 为什么还要保存 retrieval_logs？

回答思路：当回答不准确时，可以回看当时检索到了哪些 Chunk、距离是多少、是否是检索问题还是生成问题。这是后续评估和优化 RAG 的基础。
