# KnowFlow AI 后端

后端使用 FastAPI 搭建，负责提供知识库、文档管理、检索问答和执行日志等 API。

当前后端已形成完整 RAG 与轻量 Agent 链路，支持 TXT、Markdown、文本型 PDF、
流式上传、Chroma 检索、带引用问答、离线评估、请求追踪和依赖就绪检查。

第一阶段只实现工程化基础能力：

- 应用配置
- 日志配置
- 数据库连接
- 健康检查接口
- 测试骨架

第二阶段加入：

- 知识库管理接口
- 文档上传接口
- 文档元信息持久化

## 本地运行

```powershell
cd D:\ZM\agent_study\knowflow-ai\backend
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

脚本会调用真实 Embedding 和 Chroma 检索，输出 Hit Rate@K、MRR 与关键词召回率。
知识库需要提前上传并索引与评估集匹配的文档。

## 目录职责

- `app/api`：HTTP 接口层，只处理请求和响应。
- `app/services`：业务逻辑层，后续放文档解析、RAG 问答、Agent Router。
- `app/repositories`：数据访问层，负责数据库读写。
- `app/models`：SQLAlchemy 数据库模型。
- `app/schemas`：Pydantic 请求和响应结构。
- `app/core`：配置、日志等基础设施。
- `app/db`：数据库连接和 ORM 基类。

## 第二阶段接口

```text
POST   /api/knowledge-bases
GET    /api/knowledge-bases
DELETE /api/knowledge-bases/{knowledge_base_id}
POST   /api/knowledge-bases/{knowledge_base_id}/documents
GET    /api/knowledge-bases/{knowledge_base_id}/documents
```
