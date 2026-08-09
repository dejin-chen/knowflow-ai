# KnowFlow AI 后端

KnowFlow AI 后端是基于 FastAPI 的知识库与可信问答服务，负责文档接入、解析切分、混合检索、受控路由、答案生成、引用回溯、缓存和审计等核心能力。

## 核心职责

- 管理知识库、文档元信息和原始文件，支持 TXT、Markdown 与文本型 PDF。
- 以 SQLite 保存业务事实，以 Chroma 保存向量索引，并维护跨存储一致性。
- 结合 Chroma 向量召回、BM25 与加权 RRF 完成混合检索。
- 使用结构化 LLM Rerank 精排候选片段，并在模型输出异常时执行可解释降级。
- 通过受控 Agent Router 完成查询改写、检索策略选择和证据边界校验。
- 提供精确问答缓存、请求追踪、执行日志、反馈采集与离线评估能力。

## 本地运行

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 测试

```powershell
pytest
```

## 离线检索评估

```powershell
python scripts/evaluate_retrieval.py `
  --knowledge-base-id 1 `
  --dataset ..\evaluation\retrieval_dataset.example.json `
  --min-hit-rate 0.8
```

评估脚本调用实际 Embedding 与 Chroma 检索链路，输出 Hit Rate@K、MRR 和关键词召回率。执行前需为目标知识库上传并索引与评估集匹配的文档。

## 目录职责

- `app/api`：HTTP 接口与请求/响应适配。
- `app/services`：文档处理、检索问答、缓存和 Agent Router 等业务编排。
- `app/repositories`：业务数据库访问与查询封装。
- `app/models`：SQLAlchemy 数据模型。
- `app/schemas`：Pydantic 请求、响应与结构化模型输出。
- `app/core`：配置、日志、请求可观测性等基础设施。
- `app/db`：数据库连接、会话与 ORM 基类。

## 主要接口

```text
POST   /api/knowledge-bases
GET    /api/knowledge-bases
DELETE /api/knowledge-bases/{knowledge_base_id}
POST   /api/knowledge-bases/{knowledge_base_id}/documents
GET    /api/knowledge-bases/{knowledge_base_id}/documents
POST   /api/knowledge-bases/{knowledge_base_id}/search
POST   /api/knowledge-bases/{knowledge_base_id}/chat
GET    /api/conversations/{conversation_id}
POST   /api/feedback
```
