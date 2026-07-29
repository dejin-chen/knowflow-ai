# KnowFlow AI

[![KnowFlow AI CI](https://github.com/xibeiqiaozhilang-bot/knowflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/xibeiqiaozhilang-bot/knowflow-ai/actions/workflows/ci.yml)

KnowFlow AI 是一个使用 Python 开发的企业知识库 RAG 问答平台，面向 Agent
工程师和 AI 应用开发工程师岗位的应届生项目展示。

项目采用 FastAPI + Streamlit 的前后端结构，实现了从知识库管理、文档切分、
Embedding 和语义检索，到带引用问答、轻量 Agent Router、执行记录与 Docker
部署的完整链路。设计重点是结构清晰、流程可解释、能够测试，而不是堆叠复杂功能。

## 核心能力

- 知识库创建、查询和删除
- TXT、Markdown 文档上传与元信息管理
- 文本清洗、可配置 Chunk 切分和位置记录
- OpenAI 兼容 Embedding 接口与 Chroma 向量索引
- 指定知识库范围内的 Top-K 语义检索
- 带引用来源、资料不足判断和会话历史的 RAG 问答
- 普通问答、文档总结、多文档对比和信息追问的轻量 Agent Router
- Agent 执行步骤、检索日志和模型 Token 用量记录
- 回答反馈、文档摘要和自动 FAQ
- Streamlit 中文演示页面
- Docker Compose 一键启动与 GitHub Actions 自动化测试

当前仅支持 TXT 和 Markdown 文档。PDF、PostgreSQL + pgvector 和用户登录属于后续升级项。

## 系统架构

```mermaid
flowchart LR
    U["用户"] --> UI["Streamlit 中文界面"]
    UI --> API["FastAPI 接口层"]
    API --> S["业务服务层"]
    S --> AR["Agent Router"]
    AR --> RAG["RAG 问答"]
    AR --> DT["总结 / 对比 / 追问工具"]
    RAG --> EMB["Embedding API"]
    RAG --> LLM["Chat LLM API"]
    S --> DB[("SQLite")]
    S --> VS[("Chroma")]
    S --> FS[("上传文件")]
```

三类存储各自负责不同数据：

- SQLite 保存知识库、文档、Chunk 正文、会话、日志和引用关系，是业务数据来源。
- Chroma 保存 Chunk 向量、检索 metadata 和索引副本，负责语义相似度召回。
- 文件目录保存用户上传的原始文档，数据库只记录其存储路径和元信息。

详细设计见[系统架构说明](docs/system_architecture.md)。

## 核心数据流

### 文档建索引

```text
上传文档
→ 保存原文件和 documents 元信息
→ 解析、清洗并切分 Chunk
→ 将 Chunk 正文保存到 SQLite
→ 调用 Embedding 模型生成向量
→ 将向量和定位 metadata 写入 Chroma
→ 在 vector_indexes 记录 Chunk 与 Chroma 的映射
```

### RAG 问答

```text
用户问题
→ Agent Router 判断意图
→ 问题向量化
→ Chroma 在指定知识库内召回 Top-K
→ 根据 metadata 回查 SQLite 中的 Chunk 和文档来源
→ 判断检索依据是否充足
→ 构造带编号资料的 RAG Prompt
→ LLM 生成带引用回答
→ 保存消息、引用、检索日志、执行步骤和 Token 用量
```

## 技术栈

| 模块 | 技术 | 职责 |
| --- | --- | --- |
| 后端 API | FastAPI | 接收请求、参数校验、依赖注入和 OpenAPI 文档 |
| 前端 | Streamlit | 提供中文知识库管理、文档处理和问答界面 |
| ORM | SQLAlchemy | 映射 Python 模型与关系型数据库表 |
| 业务数据库 | SQLite | 保存结构化业务数据和 Chunk 正文 |
| 向量数据库 | Chroma | 保存 Embedding 并执行语义检索 |
| 模型接口 | OpenAI 兼容 API | 提供 Chat Completion 和 Embedding |
| 配置 | pydantic-settings + `.env` | 隔离环境配置和真实密钥 |
| 测试 | pytest | 验证服务、RAG 和 Agent 业务流程 |
| 部署 | Docker Compose | 统一后端、前端和持久化目录 |
| CI | GitHub Actions | 每次推送自动执行后端测试和前端检查 |

## 项目结构

```text
knowflow-ai/
├── .github/workflows/       # GitHub Actions 工作流
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI 路由
│   │   ├── core/            # 配置与日志
│   │   ├── db/              # SQLAlchemy 会话与基类
│   │   ├── models/          # 数据库模型
│   │   ├── repositories/    # 数据访问层
│   │   ├── schemas/         # API 输入输出模型
│   │   ├── services/        # RAG、Agent 和文档业务逻辑
│   │   └── main.py          # FastAPI 应用入口
│   ├── tests/               # pytest 测试
│   ├── .env.example         # 后端配置模板
│   └── Dockerfile
├── frontend/
│   ├── core/                # 前端配置
│   ├── services/            # FastAPI 客户端
│   ├── views/               # Streamlit 页面
│   ├── app.py               # Streamlit 入口
│   └── Dockerfile
├── docs/                    # 中文阶段文档和架构说明
├── sample_data/             # 可公开使用的测试知识库
└── docker-compose.yml
```

## 快速启动

### 1. 克隆项目

```powershell
git clone https://github.com/xibeiqiaozhilang-bot/knowflow-ai.git
cd knowflow-ai
```

### 2. 创建模型配置

```powershell
Copy-Item backend/.env.example backend/.env
```

在 `backend/.env` 中配置可用的 OpenAI API 或兼容接口：

```dotenv
CHAT_API_KEY=your_chat_api_key
CHAT_BASE_URL=https://your-chat-provider.example/v1
CHAT_MODEL=your_chat_model

EMBED_API_KEY=your_embedding_api_key
EMBED_BASE_URL=https://your-embedding-provider.example/v1
EMBED_MODEL_NAME=your_embedding_model
```

真实 `.env` 已被 Git 和 Docker 构建上下文忽略，不要把密钥写入源码或文档。

### 3. 使用 Docker Compose 启动

```powershell
docker compose up --build
```

启动完成后访问：

- Streamlit 页面：<http://127.0.0.1:8501>
- FastAPI 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

可以上传 [sample_data/knowflow_demo_handbook.md](sample_data/knowflow_demo_handbook.md)
体验切分、索引、检索和问答流程。

Docker 数据保存在命名卷 `knowflow_data` 中，删除并重新创建容器后，
SQLite、Chroma 和上传文件仍会保留。详细说明见
[Docker 部署文档](docs/stage_09_docker_deployment.md)。

## 本地开发

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
python -m pip install -r requirements.txt
streamlit run app.py
```

前端默认访问 `http://127.0.0.1:8000/api`，可以通过 `API_BASE_URL` 修改。

## 测试与持续集成

本地运行后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

项目现有 24 个测试，覆盖健康检查、知识库与文档、Chunk、向量索引、
RAG 问答、Agent Router、执行历史、反馈、摘要、FAQ 和模型用量记录。

GitHub Actions 会在推送到 `main`、创建 Pull Request 或手动触发时，
自动执行后端 pytest 和前端 Python 语法检查。详见
[CI 学习文档](docs/stage_09_github_actions_ci.md)。

## 设计取舍

- Router 第一版使用显式规则，便于初学者观察、测试和解释；后续可替换为 LLM 分类。
- SQLite 与 Chroma 分工存储，避免把业务正文完全绑定到某一种向量数据库。
- RAG 在最佳检索距离超过阈值时直接返回“知识库中没有足够依据”，减少无依据回答。
- 摘要、FAQ 和多文档对比会调用 LLM；普通语义检索只调用 Embedding。
- 项目暂不加入复杂权限、多租户和多 Agent 编排，优先保证完整性与可讲解性。

## 中文文档

- [系统架构说明](docs/system_architecture.md)
- [中文接口文档](docs/api_reference.md)
- [RAG 问答阶段](docs/stage_05_rag_chat.md)
- [Streamlit 页面阶段](docs/stage_06_streamlit_ui.md)
- [Agent Router 阶段](docs/stage_07_agent_router.md)
- [Docker 部署阶段](docs/stage_09_docker_deployment.md)
- [GitHub Actions CI](docs/stage_09_github_actions_ci.md)

## 后续计划

- 支持 PDF 文档解析和页码来源
- 增加 PostgreSQL + pgvector 迁移方案
- 补充用户登录与知识库访问控制
- 增加检索质量评估数据集
- 完成接口说明、简历项目描述和面试讲解稿
