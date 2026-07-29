# KnowFlow AI 后端

后端使用 FastAPI 搭建，负责提供知识库、文档管理、检索问答和执行日志等 API。

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
