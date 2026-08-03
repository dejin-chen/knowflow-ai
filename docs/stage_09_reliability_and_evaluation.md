# 第九阶段：可靠性、可观测性与检索评估

## 1. 为什么做这一组优化

一个 RAG 项目不仅要在正常输入下返回答案，还要能回答三个工程问题：

1. 用户上传大文件或损坏文件时，系统会不会占满内存或留下垃圾文件？
2. 请求失败时，开发者能不能从日志定位到同一次调用？
3. 修改 Chunk、Embedding 或 Top-K 后，怎样证明检索真的变好了？

本阶段分别用流式上传、请求可观测性和离线评估解决这些问题。

## 2. 本阶段主要文件

| 文件 | 作用 |
| --- | --- |
| `app/services/document_service.py` | 分块接收上传内容，执行大小限制与失败清理 |
| `app/services/document_parser_service.py` | 解析 TXT、Markdown 和文本型 PDF |
| `app/core/request_observability.py` | 生成或透传请求 ID，记录状态码与耗时 |
| `app/services/readiness_service.py` | 检查 SQLite 和 Chroma 是否可用 |
| `app/services/embedding_service.py` | Embedding 调用的超时、重试和错误转换 |
| `app/services/chat_completion_service.py` | Chat LLM 调用的超时、重试和错误转换 |
| `app/schemas/retrieval_evaluation.py` | 定义评估集与评估报告的数据结构 |
| `app/services/retrieval_evaluation_service.py` | 运行检索并计算评估指标 |
| `scripts/evaluate_retrieval.py` | 从命令行对真实知识库执行评估 |
| `evaluation/retrieval_dataset.example.json` | 可提交 Git 的示例人工标注集 |

## 3. 流式上传怎样工作

```text
UploadFile
→ 每次读取固定字节数
→ 累计已读取大小
→ 超过上限立即返回 413
→ 每一块写入目标文件
→ 写入完成后保存 documents 元信息
```

与 `await file.read()` 一次读取完整文件相比，流式写入让单个上传请求的内存占用主要由
`UPLOAD_READ_CHUNK_SIZE` 决定。默认文件上限是 10 MB，可以通过环境变量调整。

数据库保存失败、磁盘写入失败、文件为空或文件超限时，Service 会删除未完成文件，
避免 `uploads` 目录留下没有数据库记录的孤儿文件。

文件名还会先去除客户端路径，只保留基础名称。这样即使客户端传入 Windows 或 Linux
风格的完整路径，也不能借此决定服务器写入位置。

## 4. PDF 为什么只能支持一部分

pypdf 可以读取带文本层的 PDF，并逐页调用 `extract_text()`。项目在每页文本前加入
“第 N 页”标记，再进入统一清洗和 Chunk 流程，因此引用正文能够保留页码线索。

扫描件通常只有页面图片，没有可直接提取的字符。pypdf 不是 OCR 工具，所以系统检测到
没有有效文本时返回明确错误，而不是生成空 Chunk。后续可以接入 PaddleOCR 或云 OCR，
但这不是当前应届生项目必须承担的复杂度。

参考：[pypdf 官方文本提取说明](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)。

## 5. 请求 ID 怎样串联日志

每个 HTTP 请求进入 FastAPI 时会经过中间件：

```text
读取客户端 X-Request-ID
→ 合法则沿用，不合法或缺失则生成 UUID
→ 写入 request.state.request_id
→ 执行业务接口
→ 记录 method、path、status_code、duration_ms
→ 在响应头返回同一个 X-Request-ID
```

当用户反馈某次请求失败时，可以提供响应头中的 ID。开发者用同一个 ID 搜索日志，
就能把入口、耗时和错误关联起来。当前是单体应用，不需要引入完整链路追踪平台。

## 6. 存活检查和就绪检查

- `GET /api/health`：只证明 FastAPI 进程可以响应。
- `GET /api/health/ready`：执行 `SELECT 1`，并调用 Chroma heartbeat。

两者分开后，容器编排器可以用 readiness 决定是否分发流量，同时保留 liveness 用于判断
进程本身是否还活着。外部模型 API 没有放进 readiness，因为临时网络波动不应该触发后端
容器反复重启。

## 7. 模型超时为什么重要

Embedding 和 Chat LLM 都是外部依赖。项目通过以下配置控制调用：

```dotenv
MODEL_REQUEST_TIMEOUT_SECONDS=30
MODEL_MAX_RETRIES=1
```

超时或连接失败时返回 `503 Service Unavailable`，表示服务暂时不可用；其他上游模型错误
返回 `502 Bad Gateway`。有限重试可以吸收短暂抖动，但不能无限等待，否则一个模型故障会
持续占用 Web 请求和评估进程。

## 8. 为什么需要离线检索评估

只用肉眼问几个问题无法稳定比较两个版本。评估集把人工判断写成结构化数据：

```json
{
  "case_id": "leave-sick-001",
  "question": "连续病假超过三个工作日需要补充什么材料？",
  "expected_filenames": ["knowflow_demo_handbook.md"],
  "expected_keywords": ["正式病假证明原件", "电子材料"],
  "top_k": 3
}
```

没有直接标注 `chunk_id`，因为文档重新切分后 ID 会变化。文件名与关键事实词更稳定，
同时仍能检查检索结果是不是来自正确文档、包含正确证据。

## 9. 三个评估指标

### Hit Rate@K

前 K 个结果中只要出现至少一个正确证据，该题记为 1，否则为 0；对所有题取平均。
它回答：“正确资料有没有被找回来？”

### MRR

取第一个正确证据排名的倒数。例如排第 1 得 1，排第 2 得 0.5，没有命中得 0，
再对所有题取平均。它回答：“正确资料是否排得足够靠前？”

### 关键词召回率

统计预期来源的召回 Chunk 中覆盖了多少人工标注关键词。它是当前项目的轻量证据完整性
指标，不等同于答案正确率，也不能替代人工评审。

## 10. 怎样运行评估

先把 `sample_data/knowflow_demo_handbook.md` 上传到知识库，完成 Chunk 和向量索引，
再在 `backend` 目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_retrieval.py `
  --knowledge-base-id 1 `
  --dataset ..\evaluation\retrieval_dataset.example.json `
  --min-hit-rate 0.8
```

脚本只调用 Embedding 和向量检索，不调用 Chat LLM。`--min-hit-rate` 是可选质量门槛，
低于门槛时进程返回非零退出码，未来可以接入 CI。

## 11. 正确的优化方式

```text
运行基线评估并保存报告
→ 修改 chunk_size、overlap、Top-K、Embedding 或检索策略
→ 对同一知识库和同一评估集重新建索引
→ 再次评估
→ 比较指标和失败样例
```

不能只看总分。某个指标下降时，应检查具体题目的来源文件、首个命中排名和关键词覆盖，
再判断是切分边界、Embedding、排序还是标注本身的问题。

## 12. 本阶段测试

完成轻量 Rerank 时项目共有 50 个 pytest 测试；升级 LLM Rerank 后当前共有 57 个。本阶段新增覆盖：

- 超限上传立即拒绝并删除临时文件；
- PDF 文件名安全处理、页码提取和扫描件拒绝；
- 请求 ID 自动生成与透传；
- SQLite 与 Chroma readiness；
- 模型超时转换为 `503`；
- Hit Rate@K、MRR 和关键词召回率计算。

## 13. 简历表述

> 建立可版本化的 RAG 离线检索评估集，计算 Hit Rate@K、MRR 和关键词召回率；
> 实现流式文件上传、PDF 文本提取、请求 ID、依赖就绪检查与模型超时保护，
> 并通过 pytest 覆盖异常清理和指标计算等关键路径。
