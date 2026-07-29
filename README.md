# KnowFlow AI

[![KnowFlow AI CI](https://github.com/xibeiqiaozhilang-bot/knowflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/xibeiqiaozhilang-bot/knowflow-ai/actions/workflows/ci.yml)

## Docker 启动

准备好 `backend/.env` 中的模型配置后，在项目根目录执行：

```powershell
docker compose up --build
```

详细说明见 `docs/stage_09_docker_deployment.md`。

KnowFlow AI 是一个面向应届生简历展示的 Python 企业知识库 RAG 问答平台。

项目目标不是做一个单文件 RAG Demo，而是按正式 AI 应用的方式逐步搭建：后端使用 FastAPI，前端使用 Streamlit，结构化数据先存 SQLite，向量检索后续使用 Chroma，模型调用兼容 OpenAI API。

## 当前阶段

已完成第一至第五阶段的后端核心链路：

- FastAPI + SQLite + SQLAlchemy 工程骨架与健康检查
- 知识库管理、TXT/Markdown 上传与文档元信息管理
- 文档解析、文本清洗与可配置 Chunk 切分
- OpenAI 兼容 Embedding、Chroma 向量索引与知识库范围语义检索
- 带真实引用来源的 RAG 问答、会话消息与检索日志持久化
- Streamlit 中文演示工作台，覆盖知识库管理、文档处理、历史会话与引用问答

## 项目结构

```text
knowflow-ai
├── backend
│   ├── app
│   │   ├── api
│   │   ├── core
│   │   ├── db
│   │   ├── models
│   │   ├── repositories
│   │   ├── schemas
│   │   ├── services
│   │   └── main.py
│   └── tests
├── frontend
└── docs
```

## 后端启动

```powershell
cd D:\ZM\agent_study\knowflow-ai\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

健康检查地址：

```text
http://127.0.0.1:8000/api/health
```

## 前端启动

```powershell
cd D:\ZM\agent_study\knowflow-ai\frontend
pip install -r requirements.txt
streamlit run app.py
```

## 配置说明

复制后端配置示例：

```powershell
cd D:\ZM\agent_study\knowflow-ai\backend
copy .env.example .env
```

真实 API Key 只放在 `.env`，不要写进代码、README 或测试输出。

## 学习重点

当前你应该能讲清楚：

- 文档如何从原始文件变为 Chunk，再变为向量索引
- Chroma metadata 如何与 SQLite 共同完成引用溯源
- RAG Prompt 如何将检索资料、回答边界和用户问题交给 LLM
- 为什么会话、消息和 retrieval logs 是可观测 RAG 系统的基础
