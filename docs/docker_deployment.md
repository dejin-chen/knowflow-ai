# Docker Compose 部署

## 1. 部署目标

本机直接启动项目时，需要分别准备 Python、安装依赖，并手动启动 FastAPI 和 Streamlit。Docker 将这些运行条件写入镜像配置，其他人拿到项目后可以用一条命令启动相同的服务组合。

本项目由两个容器组成：

```text
浏览器
  |
  v
Streamlit 容器 :8501  ---->  FastAPI 容器 :8000
                                      |
                                      v
                       SQLite + Chroma + 上传文件（Docker 数据卷）
```

## 2. 配置模型密钥

Docker 配置不会保存真实密钥。启动前，在 `backend/.env` 中配置模型相关变量，例如：

```env
CHAT_API_KEY=你的聊天模型密钥
CHAT_BASE_URL=兼容 OpenAI 的聊天接口地址
CHAT_MODEL=聊天模型名称
EMBED_API_KEY=你的 Embedding 模型密钥
EMBED_BASE_URL=兼容 OpenAI 的 Embedding 接口地址
EMBED_MODEL_NAME=Embedding 模型名称
```

`backend/.env` 被 `.gitignore` 忽略，不能提交到仓库。

## 3. 启动与停止

在项目根目录执行：

```powershell
docker compose up --build
```

启动成功后访问：

- Streamlit 页面：`http://127.0.0.1:8501`
- FastAPI 接口文档：`http://127.0.0.1:8000/docs`

停止服务：

```powershell
docker compose down
```

## 4. 数据为什么不会丢失

`docker-compose.yml` 将后端 `/app/data` 挂载为命名卷 `knowflow_data`。SQLite 数据库、Chroma 持久化文件和上传文档都保存在这个卷中，因此 `docker compose down` 后再次启动，知识库数据仍在。

注意：`docker compose down -v` 会额外删除数据卷，只应在需要清空测试数据时使用。

## 5. 部署设计说明

部署设计摘要：

> Docker Compose 将 FastAPI RAG 后端与 Streamlit 管理控制台拆分为两个服务；容器通过服务名通信，并使用命名卷持久化 SQLite、Chroma 向量索引和上传文档，避免容器重建导致知识库数据丢失。模型密钥通过未提交的环境变量文件注入。
