# KnowFlow AI 接口文档

## 1. 访问地址

本地或 Docker 启动后的默认地址：

| 用途 | 地址 |
| --- | --- |
| API 基础地址 | `http://127.0.0.1:8000/api` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| 健康检查 | `http://127.0.0.1:8000/api/health` |
| 就绪检查 | `http://127.0.0.1:8000/api/health/ready` |

Swagger UI 适合直接查看 Schema 和调试接口，本文件重点解释接口在业务流程中的作用。

## 2. 通用约定

### 数据格式

- 普通请求和响应使用 `application/json`。
- 上传文档使用 `multipart/form-data`，表单字段名为 `file`。
- 时间字段使用 ISO 8601 格式，例如 `2026-07-29T16:00:00`。
- 资源 ID 是 SQLite 自增整数。
- 每个响应都包含 `X-Request-ID`。客户端传入合法值时后端沿用，否则自动生成，便于关联日志。

### 错误结构

业务错误通常返回：

```json
{
  "detail": "知识库不存在"
}
```

参数校验失败通常返回 `422`，其中 `detail` 是字段错误列表。

### 推荐调用顺序

```text
POST /knowledge-bases
→ POST /knowledge-bases/{knowledge_base_id}/documents
→ POST /documents/{document_id}/chunks
→ POST /documents/{document_id}/index
→ POST /knowledge-bases/{knowledge_base_id}/search
→ POST /knowledge-bases/{knowledge_base_id}/chat
```

文档必须先完成 Chunk 切分，才能建立向量索引。问答前应先建立索引，否则没有可检索资料。

## 3. 接口总览

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/health/ready` | 检查 SQLite 与 Chroma 是否就绪 |
| POST | `/knowledge-bases` | 创建知识库 |
| GET | `/knowledge-bases` | 获取知识库列表 |
| DELETE | `/knowledge-bases/{knowledge_base_id}` | 删除知识库 |
| POST | `/knowledge-bases/{knowledge_base_id}/documents` | 上传文档 |
| GET | `/knowledge-bases/{knowledge_base_id}/documents` | 获取文档列表 |
| POST | `/documents/{document_id}/chunks` | 解析并切分文档 |
| GET | `/documents/{document_id}/chunks` | 查看文档 Chunk |
| POST | `/documents/{document_id}/index` | 建立向量索引 |
| GET | `/documents/{document_id}/summary` | 获取已生成摘要 |
| POST | `/documents/{document_id}/summary` | 生成或更新摘要 |
| GET | `/documents/{document_id}/faqs` | 获取 FAQ |
| POST | `/documents/{document_id}/faqs` | 生成或替换 FAQ |
| POST | `/knowledge-bases/{knowledge_base_id}/search` | 语义检索 |
| POST | `/knowledge-bases/{knowledge_base_id}/chat` | RAG / Agent 问答 |
| GET | `/knowledge-bases/{knowledge_base_id}/cache/stats` | 查看回答缓存统计 |
| DELETE | `/knowledge-bases/{knowledge_base_id}/cache` | 手动清空回答缓存 |
| GET | `/knowledge-bases/{knowledge_base_id}/conversations` | 获取会话列表 |
| GET | `/conversations/{conversation_id}/messages` | 获取会话消息 |
| POST | `/messages/{assistant_message_id}/feedback` | 提交回答反馈 |

表中的路径都需要加上 `/api` 前缀。

## 4. 健康检查

### `GET /api/health`

检查 FastAPI 应用是否已经启动。

响应状态：`200 OK`

```json
{
  "status": "ok",
  "service": "KnowFlow AI",
  "version": "0.1.0",
  "environment": "development"
}
```

健康检查只证明 Web 应用能够响应，不代表模型 API 一定可用。

### `GET /api/health/ready`

检查 API 当前能否访问 SQLite 和 Chroma。两个依赖都正常时返回：

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "vector_store": "ok"
  }
}
```

依赖异常时返回 `503`。Docker Compose 使用该接口判断后端是否可以接收业务请求。
外部模型 API 不进入就绪检查，避免临时网络波动让整个后端被容器编排器反复重启。

## 5. 知识库管理

### 创建知识库

`POST /api/knowledge-bases`

请求：

```json
{
  "name": "企业制度库",
  "description": "保存员工手册、报销制度和项目规范"
}
```

字段约束：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 长度 1 到 100，保存前去除首尾空格 |
| `description` | string / null | 否 | 知识库说明 |

响应状态：`201 Created`

```json
{
  "id": 1,
  "name": "企业制度库",
  "description": "保存员工手册、报销制度和项目规范",
  "created_at": "2026-07-29T16:00:00",
  "updated_at": "2026-07-29T16:00:00"
}
```

### 获取知识库列表

`GET /api/knowledge-bases`

响应状态：`200 OK`

返回 `KnowledgeBaseRead` 数组，没有数据时返回 `[]`。

### 删除知识库

`DELETE /api/knowledge-bases/{knowledge_base_id}`

响应状态：

- `204 No Content`：删除成功，无响应正文。
- `404 Not Found`：知识库不存在。

当前实现会先清理该知识库的 Chroma 向量，再删除关系型数据库中的关联业务数据，
最后删除上传目录中的原始文件。Chroma 清理失败时返回 `503`，并保留 SQLite 主数据。

## 6. 文档管理与处理

### 上传文档

`POST /api/knowledge-bases/{knowledge_base_id}/documents`

请求格式：`multipart/form-data`

PowerShell 示例：

```powershell
curl.exe -X POST `
  "http://127.0.0.1:8000/api/knowledge-bases/1/documents" `
  -F "file=@sample_data/knowflow_demo_handbook.md"
```

当前支持扩展名：

- `.txt`
- `.md`
- `.markdown`
- `.pdf`（文本型 PDF）

后端使用固定大小的数据块流式写入磁盘，不会先把整个上传文件读入内存。默认上限为
10 MB，可通过 `MAX_UPLOAD_SIZE_MB` 调整；写入失败、文件为空或超限时会清理未完成文件。

响应状态：`201 Created`

```json
{
  "id": 1,
  "knowledge_base_id": 1,
  "filename": "knowflow_demo_handbook.md",
  "file_type": "md",
  "file_size": 5320,
  "status": "uploaded",
  "created_at": "2026-07-29T16:05:00",
  "summary": null,
  "faqs": []
}
```

常见错误：

- `400`：文件为空，或不是 TXT/Markdown/PDF。
- `404`：目标知识库不存在。
- `413`：文件超过配置的上传大小上限。

### 获取知识库文档

`GET /api/knowledge-bases/{knowledge_base_id}/documents`

返回该知识库的 `DocumentRead` 数组。每条记录可以包含已经保存的摘要和 FAQ。

### 解析并切分文档

`POST /api/documents/{document_id}/chunks`

该接口依次完成：

```text
读取原始文件
→ 文本文件使用 UTF-8 或 GB18030 解码；PDF 逐页提取文本
→ 清洗文本
→ 按 chunk_size 和 chunk_overlap 切分
→ 保存 document_chunks
→ 将文档状态改为 chunked
```

接口没有请求正文。

响应状态：`201 Created`

```json
{
  "document_id": 1,
  "status": "chunked",
  "chunk_count": 13
}
```

重复调用会先清理该文档旧的 Chroma 向量，再在同一个 SQLite 事务中替换 Chunk，
同时删除基于旧 Chunk 生成的摘要和 FAQ，最后将文档状态恢复为 `chunked`。

PDF 解析会在正文中插入“第 N 页”标记，后续 Chunk 和引用可以保留页码线索。
扫描版 PDF 没有可提取文本时返回 `400`，当前版本不做 OCR。

常见错误：

- `400`：文档没有有效文本、类型不支持或编码无法识别。
- `404`：文档或原始文件不存在。

### 查看 Chunk

`GET /api/documents/{document_id}/chunks`

响应示例：

```json
[
  {
    "id": 1,
    "document_id": 1,
    "knowledge_base_id": 1,
    "chunk_index": 0,
    "content": "员工申请病假时，需要提供医院出具的证明材料。",
    "char_count": 25,
    "start_offset": 0,
    "end_offset": 25,
    "created_at": "2026-07-29T16:06:00"
  }
]
```

`start_offset` 和 `end_offset` 表示 Chunk 在清洗后文本中的字符位置。

### 建立向量索引

`POST /api/documents/{document_id}/index`

该接口没有请求正文，执行：

```text
读取 SQLite 中的 Chunk 正文
→ 调用 Embedding API
→ 写入 Chroma
→ 保存 vector_indexes 映射
→ 将文档状态改为 indexed
```

响应状态：`201 Created`

```json
{
  "document_id": 1,
  "indexed_chunk_count": 13,
  "status": "indexed"
}
```

常见错误：

- `400`：文档尚未切分。
- `404`：文档不存在。
- `500`：没有配置 Embedding API Key。
- `502`：Embedding 模型返回上游错误。
- `503`：Chroma 写入失败，或模型连接/请求超时。

## 7. 文档摘要与 FAQ

### 生成文档摘要

`POST /api/documents/{document_id}/summary`

前置条件：文档状态必须是 `chunked` 或 `indexed`。

该接口读取文档 Chunk、构造总结 Prompt、调用聊天模型，并保存摘要、引用和
Token 用量。重复调用会更新已有摘要。

响应示例：

```json
{
  "id": 1,
  "document_id": 1,
  "content": "该文档主要介绍员工考勤、休假和报销制度。",
  "citations": [
    {
      "reference_id": 1,
      "chunk_id": 1,
      "document_id": 1,
      "filename": "员工手册.md",
      "chunk_index": 0,
      "content": "员工申请病假时，需要提供医院出具的证明材料。",
      "distance": null
    }
  ],
  "model_name": "your_chat_model",
  "prompt_tokens": 800,
  "completion_tokens": 180,
  "total_tokens": 980,
  "created_at": "2026-07-29T16:10:00",
  "updated_at": "2026-07-29T16:10:00"
}
```

常见错误：

- `404`：文档不存在。
- `409`：文档尚未切分，或没有可总结文本。
- `500`：没有配置聊天模型 API Key。
- `502`：聊天模型调用失败，或没有返回有效回答。

### 获取文档摘要

`GET /api/documents/{document_id}/summary`

没有生成过摘要时返回 `404`。

### 生成 FAQ

`POST /api/documents/{document_id}/faqs`

前置条件：必须先生成文档摘要，并且摘要包含可追溯引用。

系统要求模型返回 4 条结构化 FAQ，并校验问题、回答和引用编号。
重复生成会替换旧 FAQ。

响应是 `DocumentFaqRead` 数组：

```json
[
  {
    "id": 1,
    "document_id": 1,
    "question": "连续病假需要提供什么材料？",
    "answer": "需要根据制度提供有效病假证明。",
    "citations": [
      {
        "reference_id": 1,
        "chunk_id": 1,
        "filename": "员工手册.md"
      }
    ],
    "sort_order": 1,
    "created_at": "2026-07-29T16:12:00"
  }
]
```

常见错误：

- `404`：文档不存在。
- `409`：尚未生成摘要，或摘要没有引用。
- `502`：模型输出不是系统要求的 FAQ 结构。
- `500`：没有配置聊天模型 API Key。

### 获取 FAQ

`GET /api/documents/{document_id}/faqs`

没有生成 FAQ 时返回空数组 `[]`。

## 8. 语义检索

### `POST /api/knowledge-bases/{knowledge_base_id}/search`

只执行 Embedding 和向量检索，不调用聊天模型。

请求：

```json
{
  "query": "连续病假需要什么证明？",
  "top_k": 5
}
```

字段约束：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `query` | string | 是 | 去除空格后长度 1 到 1000 |
| `top_k` | integer | 否 | 1 到 10，默认 5 |

响应：

```json
[
  {
    "chunk_id": 1,
    "document_id": 1,
    "knowledge_base_id": 1,
    "filename": "员工手册.md",
    "chunk_index": 0,
    "content": "员工申请病假时，需要提供医院出具的证明材料。",
    "distance": 0.2135
  }
]
```

`distance` 是 Chroma 返回的余弦距离，通常越小表示语义越接近。
它不是百分制相似度，不应显示成“78.65% 准确率”。

系统默认先向 Chroma 请求 `top_k × 3` 个候选，回查 SQLite 后，按
“同一文档 + 规范化正文”去除完全重复内容，再保留最终 Top-K。这样可以避免
重复 Chunk 占满引用，同时允许不同文档保留相同制度内容作为独立来源。

## 9. RAG 与 Agent 问答

### `POST /api/knowledge-bases/{knowledge_base_id}/chat`

请求：

```json
{
  "question": "连续病假超过三个工作日需要什么材料？",
  "conversation_id": null,
  "top_k": 3
}
```

字段约束：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `question` | string | 是 | 去除空格后长度 1 到 2000 |
| `conversation_id` | integer / null | 否 | 为空时创建新会话 |
| `top_k` | integer / null | 否 | 1 到 10；为空时使用后端配置 |

Router 可能返回四种 `intent`：

| intent | 含义 | 工具 |
| --- | --- | --- |
| `knowledge_qa` | 普通知识库问答 | `search_knowledge_base` |
| `document_summary` | 总结指定文档 | `summarize_document` |
| `document_comparison` | 对比多份文档 | `compare_documents` |
| `clarification` | 文档信息不足 | `ask_clarifying_question` |

普通问答响应示例：

```json
{
  "conversation_id": 1,
  "assistant_message_id": 2,
  "answer": "连续病假超过三个工作日时，需要提交有效病假证明。[1]",
  "citations": [
    {
      "reference_id": 1,
      "chunk_id": 1,
      "document_id": 1,
      "filename": "员工手册.md",
      "chunk_index": 0,
      "content": "员工申请病假时，需要提供医院出具的证明材料。",
      "distance": 0.2135
    }
  ],
  "retrieved_chunk_count": 3,
  "insufficient_evidence": false,
  "cache_hit": false,
  "intent": "knowledge_qa",
  "execution_steps": [
    {
      "step_order": 1,
      "name": "意图识别",
      "tool_name": "search_knowledge_base",
      "status": "completed",
      "detail": "识别为 knowledge_qa，将调用 search_knowledge_base。"
    },
    {
      "step_order": 2,
      "name": "工具执行",
      "tool_name": "search_knowledge_base",
      "status": "completed",
      "detail": "返回 3 个检索片段。"
    }
  ],
  "model_usages": [
    {
      "id": 1,
      "assistant_message_id": 2,
      "operation": "knowledge_qa",
      "model_name": "your_chat_model",
      "prompt_tokens": 950,
      "completion_tokens": 100,
      "total_tokens": 1050,
      "created_at": "2026-07-29T16:20:00"
    }
  ]
}
```

如果没有检索结果，或最佳距离超过配置阈值：

```json
{
  "answer": "知识库中没有足够依据。",
  "citations": [],
  "retrieved_chunk_count": 0,
  "insufficient_evidence": true,
  "cache_hit": false,
  "intent": "knowledge_qa",
  "model_usages": []
}
```

实际响应仍包含 `conversation_id`、`assistant_message_id` 和执行步骤。
资料不足时不会调用聊天模型，因此 `model_usages` 为空。

当用户说“请总结这份文档”但没有提供可匹配文件名时，Router 返回
`clarification`，不执行检索或 LLM 调用。

### 回答缓存

普通问答会先使用知识库、规范化问题、Top-K、模型与检索配置生成缓存键。命中时
`cache_hit=true`，`model_usages=[]`，系统复用原回答、引用和检索证据，但仍保存本轮会话记录。

`GET /api/knowledge-bases/{knowledge_base_id}/cache/stats`

```json
{
  "knowledge_base_id": 1,
  "enabled": true,
  "ttl_seconds": 3600,
  "entry_count": 8,
  "hit_count": 21,
  "estimated_chat_tokens_saved": 18640
}
```

`estimated_chat_tokens_saved` 使用“缓存命中次数 × 首次回答总 Token”估算，只统计省去的 Chat LLM
Token，不包含 Embedding Token，也不等同于费用账单。

`DELETE /api/knowledge-bases/{knowledge_base_id}/cache`

```json
{
  "knowledge_base_id": 1,
  "deleted_entry_count": 8
}
```

文档重新切分、建立新索引或删除知识库时会自动失效缓存；手动接口用于调试或配置变更后立即清理。

## 10. 会话历史

### 获取知识库会话

`GET /api/knowledge-bases/{knowledge_base_id}/conversations`

返回：

```json
[
  {
    "id": 1,
    "knowledge_base_id": 1,
    "title": "连续病假超过三个工作日需要什么材料？",
    "created_at": "2026-07-29T16:20:00",
    "updated_at": "2026-07-29T16:20:02"
  }
]
```

### 获取会话消息

`GET /api/conversations/{conversation_id}/messages`

每条 `MessageRead` 包含：

- `role` 和 `content`
- 助手消息的结构化引用
- Agent 意图和执行步骤
- 用户反馈
- 模型名称与 Token 用量

会话不存在时返回 `404`。

## 11. 回答反馈

### `POST /api/messages/{assistant_message_id}/feedback`

只能对助手消息提交反馈。

请求：

```json
{
  "feedback_type": "helpful",
  "comment": "引用来源清晰"
}
```

`feedback_type` 只能是：

- `helpful`
- `unhelpful`

响应：

```json
{
  "feedback": {
    "id": 1,
    "assistant_message_id": 2,
    "feedback_type": "helpful",
    "comment": "引用来源清晰",
    "created_at": "2026-07-29T16:25:00"
  },
  "created": true
}
```

每条助手消息只保存一份反馈。重复提交不会覆盖原反馈，
而是返回原记录并将 `created` 设为 `false`。

## 12. 常见状态码

| 状态码 | 含义 | 本项目中的常见场景 |
| --- | --- | --- |
| `200` | 请求成功 | 查询、检索、聊天、摘要和 FAQ |
| `201` | 已创建 | 创建知识库、上传文档、生成 Chunk、建立索引 |
| `204` | 成功但没有正文 | 删除知识库 |
| `400` | 请求内容不符合业务要求 | 文件类型错误、空文件、未切分就建索引 |
| `404` | 资源不存在 | 知识库、文档、会话或助手消息不存在 |
| `409` | 当前资源状态不允许操作 | 未切分就生成摘要、未生成摘要就生成 FAQ |
| `413` | 请求体过大 | 上传文档超过配置上限 |
| `422` | Pydantic 参数校验失败 | 问题为空、Top-K 超出范围 |
| `500` | 服务端配置不完整 | 没有配置聊天或 Embedding API Key |
| `502` | 上游模型调用或输出错误 | 模型请求失败、FAQ 结构不符合要求 |
| `503` | 依赖暂时不可用 | SQLite/Chroma 异常，或模型连接和请求超时 |

## 13. 初学者应理解的数据流

以聊天接口为例：

```text
Streamlit
→ ApiClient.post()
→ FastAPI 路由
→ ChatRequest 参数校验
→ AgentChatService
→ Router 和对应工具
→ Repository / Chroma / 模型 API
→ ChatResponse
→ Streamlit 展示回答、引用和执行步骤
```

路由中的几行代码不是完整业务。路由负责“接收和返回”，真正的数据流组织在
Service 中，数据库查询封装在 Repository 中。

## 14. 面试讲解

可以这样说明接口设计：

> 项目通过 FastAPI 和 Pydantic 定义稳定的接口合同，API 层负责 HTTP 和校验，
> Service 层组织文档处理、RAG 与 Agent 流程，Repository 层封装数据库访问。
> 文档上传、Chunk、索引被拆成独立接口，便于展示各处理状态和定位失败阶段；
> 聊天接口统一返回回答、引用、意图、执行步骤与模型用量，支持前端可观测展示。

常见追问：

1. 为什么上传、切分和索引不合并成一个接口？
2. 为什么接口使用 Schema，而不是直接返回 SQLAlchemy Model？
3. `400`、`409` 和 `422` 应该如何区分？
4. 为什么聊天响应要返回结构化引用，而不只返回一段字符串？
5. 为什么语义检索接口和 RAG 聊天接口需要分开？
