# Streamlit 知识库管理控制台

## 控制台目标

控制台将 FastAPI 接口组织为知识库管理与检索验证流程。前端使用 Streamlit，只负责交互与后端调用，不直接访问 SQLite、Chroma 或模型服务。

```text
浏览器
  ↓
Streamlit 页面
  ↓ HTTP 请求
FastAPI
  ↓
SQLite / Chroma / Embedding / LLM
```

## 页面结构

### 知识库管理

- 创建知识库
- 查看知识库列表
- 上传 TXT / Markdown 文档
- 查看文档状态
- 删除知识库

### 文档处理

根据 `documents.status` 显示不同操作：

```text
uploaded -> 生成检索片段
chunked  -> 建立向量索引
indexed  -> 可问答
```

### 智能问答

- 选择当前知识库
- 创建或加载历史会话
- 发送问题
- 显示回答
- 展示引用来源和命中片段
- 显示资料不足状态

## 前端模块职责

- `app.py`：初始化页面、侧边栏知识库选择与页面路由。
- `core/config.py`：读取 `API_BASE_URL`，前端不保存模型密钥。
- `services/api_client.py`：封装所有 FastAPI 请求和错误处理。
- `views/knowledge_base_page.py`：知识库创建、上传、文档列表与删除。
- `views/document_processing_page.py`：Chunk 与向量索引操作。
- `views/chat_page.py`：聊天、引用展示和历史会话加载。

## Streamlit session_state

Streamlit 在用户每次交互后会重新执行页面脚本，因此需要将前端会话状态保存在 `st.session_state`：

- `selected_knowledge_base_id`：当前选择的知识库。
- `current_conversation_id`：当前聊天会话。
- `chat_messages`：当前显示的聊天消息。

当用户切换知识库时，前端会清空当前会话状态，避免不同知识库的消息混在一起。

## 历史会话接口

为展示已持久化的问答历史，新增：

```text
GET /api/knowledge-bases/{knowledge_base_id}/conversations
GET /api/conversations/{conversation_id}/messages
```

前端从这些接口读取 `conversations` 与 `messages` 表，不依赖浏览器临时状态。

## 实现总结

- Streamlit 能以 Python 快速构建内部知识库运营控制台，降低独立前端尚未接入时的实施成本。
- 前端应通过 FastAPI 调用业务能力，而不是直接操作数据库或模型。
- `session_state` 用于保存当前浏览器会话状态；持久化历史仍应从后端数据库读取。
- 文档处理状态可以把复杂的 RAG 预处理流程变成用户可理解的操作步骤。
- 回答与引用来源分开展示，能让用户检查结论依据。

## 实现结果

> 基于 Streamlit 构建企业知识库管理控制台，覆盖知识库管理、文档上传、Chunk 切分、向量索引、会话历史和带引用问答；通过统一 API Client 调用 FastAPI 后端，实现前后端职责分离与 RAG 全链路可视化。

## 关键设计决策

1. 为什么 Streamlit 不直接访问 Chroma 或 SQLite？

决策说明：后端负责业务规则、权限和数据一致性，前端只通过 API 调用，使前端技术栈可替换，并避免业务逻辑散落在页面代码中。

2. Streamlit 每次交互重新运行，聊天状态怎么保留？

决策说明：当前页面状态保存在 `st.session_state`，例如当前知识库和 conversation ID；完整历史消息仍通过 FastAPI 从 SQLite 的 conversations 和 messages 表读取。
