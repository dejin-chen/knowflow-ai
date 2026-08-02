# KnowFlow AI 前端

前端使用 Streamlit，用于快速演示企业知识库问答流程。

当前页面包含：

- 知识库创建、列表和删除
- TXT / Markdown / 文本型 PDF 文档上传与状态查看
- Chunk 切分和向量索引操作
- RAG 聊天问答
- 回答引用来源、命中片段和当前会话历史展示

前端不直接访问 SQLite、Chroma 或模型服务，只调用 FastAPI 后端接口。

## 启动

```powershell
cd D:\ZM\agent_study\knowflow-ai\frontend
pip install -r requirements.txt
streamlit run app.py
```

默认后端地址为 `http://127.0.0.1:8000/api`。如需修改，参考 `.env.example` 创建前端 `.env` 并设置 `API_BASE_URL`。
