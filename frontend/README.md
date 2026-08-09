# KnowFlow AI 管理控制台

前端基于 Streamlit 构建，为知识库运营、检索验证和可信问答提供统一控制台。

## 功能范围

- 创建、查看和删除知识库。
- 上传 TXT、Markdown 与文本型 PDF，并查看文档处理状态。
- 执行文档切分、向量索引与检索验证。
- 发起带引用来源的知识库问答。
- 查看命中片段、回答证据和当前会话历史。

控制台只通过 FastAPI 接口访问后端能力，不直接连接 SQLite、Chroma 或模型服务，以保持访问边界清晰。

## 启动

```powershell
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

默认后端地址为 `http://127.0.0.1:8000/api`。如需调整，请参考 `.env.example` 创建前端 `.env` 并设置 `API_BASE_URL`。
