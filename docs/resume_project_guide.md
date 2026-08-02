# KnowFlow AI 简历与面试讲解

## 1. 项目基本信息

**项目名称：** KnowFlow AI 企业知识库 RAG 问答平台  
**项目地址：** <https://github.com/xibeiqiaozhilang-bot/knowflow-ai>  
**目标岗位：** Agent 工程师 / AI 应用开发工程师  
**技术栈：** Python、FastAPI、Streamlit、SQLAlchemy、SQLite、Chroma、
OpenAI 兼容 API、pytest、Docker Compose、GitHub Actions

## 2. 简历项目描述

推荐使用下面五条，根据简历空间保留 3 到 5 条：

1. 基于 FastAPI、Streamlit、SQLAlchemy 和 Chroma 独立开发企业知识库 RAG
   问答平台，完成知识库管理、文档切分、Embedding、语义检索、带引用问答和会话持久化，
   支持 TXT、Markdown 和文本型 PDF，提供 21 个 API 操作与中文演示页面。
2. 设计轻量 Agent Router，通过结构化意图在知识问答、文档总结、多文档对比和信息追问
   4 类工具之间路由，并持久化 Agent 执行步骤、检索日志和模型 Token 用量。
3. 实现 RAG 索引生命周期治理，在文档重处理和知识库删除场景下联动清理 SQLite、
   Chroma 与原始文件；使用事务、失败补偿和派生数据失效机制降低悬空向量与过期引用风险。
4. 建立带 TTL、配置签名、索引变更失效和两级 LRU 容量治理的高频回答缓存，命中时跳过
   Embedding 与 Chat LLM；使用离线评估集计算 Hit Rate@K、MRR 和关键词召回率。
5. 使用 pytest 建立 46 个自动化测试，并通过 Docker Compose 统一前后端运行环境，
   配置 GitHub Actions 在主分支推送和 Pull Request 时自动执行后端测试与前端检查。

### 精简版本

简历空间较少时使用：

> 基于 FastAPI、Streamlit、SQLite 与 Chroma 开发企业知识库 RAG 平台，
> 实现文档切分、向量检索、带引用问答和 4 类意图 Agent Router；设计跨 SQLite、
> Chroma 和文件存储的索引生命周期与失败补偿机制，增加高频回答缓存、可量化检索评估与
> 请求可观测性，并使用 46 个 pytest 测试、
> Docker Compose 和 GitHub Actions 保障交付质量。

## 3. 不要写进简历的表述

以下描述超过项目当前能力，不建议使用：

- “生产级高并发企业平台”
- “支持海量文档”
- “实现复杂多 Agent 自主协作”
- “检索准确率达到 95%”
- “完整支持多租户和权限管理”

当前项目的优势是完整、可解释、能运行和有测试，不需要虚构规模指标。

## 4. 三分钟面试讲解

### 第一部分：项目目标

> 我做的是一个企业知识库 RAG 问答平台。用户可以创建知识库、上传 TXT、Markdown
> 或文本型 PDF，系统完成切分和向量索引，之后可以进行带真实引用的问答。
> 我没有从单文件 Demo 开始，而是按 API、Service、Repository 和 Model 分层实现。

### 第二部分：索引链路

> 文档上传后，原文件保存在 uploads，元信息写入 SQLite。处理接口读取文件并按
> chunk_size 和 overlap 切分，Chunk 正文仍保存在 SQLite。建立索引时只对正文生成
> Embedding，把向量及 chunk_id、document_id、knowledge_base_id 等 metadata 写入
> Chroma，并通过 vector_indexes 记录映射。

### 第三部分：问答链路

> 用户提问后，问题先生成向量，Chroma 在指定知识库内扩大召回候选。后端根据
> chunk_id 回查 SQLite，去除同一文档的重复正文，再构造带编号来源的 Prompt。
> 如果最佳距离超过阈值，就直接返回知识库依据不足，不调用聊天模型。

### 第四部分：Agent

> 在 RAG 之前我加入了轻量 Router。它可以把问题路由到普通问答、文档总结、
> 多文档对比或追问工具，并记录意图和执行步骤。当前 Router 使用显式规则，
> 优点是稳定、可测试、没有额外模型费用；未来可以在不改变工具合同的情况下替换成 LLM 分类。

### 第五部分：最有价值的优化

> 项目中最有挑战的是多存储一致性。文档重新切分后，旧 Chroma 向量、摘要和 FAQ
> 都必须失效。我使用 SQLite 事务原子替换关系数据；Chroma 无法加入同一事务，
> 因此在数据库失败时补偿删除本次向量。删除知识库时也会联动清理向量和上传文件。

### 第六部分：工程保障

> 项目现在有 21 个 API 操作、14 张业务表和 46 个测试。Docker Compose 负责统一运行环境，
> GitHub Actions 在每次推送后自动运行测试。我还增加了请求 ID、就绪检查、模型超时和
> 离线检索评估。当前边界是扫描 PDF 不支持 OCR，也没有登录、多租户、混合检索和 Rerank。

## 5. 高频面试问题

### 1. 为什么同时使用 SQLite 和 Chroma？

SQLite 适合保存文档关系、Chunk 正文、会话和日志，支持结构化查询与事务。
Chroma 擅长保存向量并进行相似度搜索。业务数据不完全绑定向量库，未来替换 pgvector
时不需要重建全部上层模型。

### 2. Chroma 找到向量后为什么还要回查 SQLite？

Chroma 返回 chunk_id 和距离，SQLite 才是最终业务正文和来源信息的主数据。
回查还能确认 Chunk 是否存在、是否属于当前知识库，并保持 Chroma 的排序。

### 3. vector_indexes 表有什么作用？

它记录 Chunk 和向量库记录的映射及索引状态，便于审计、重建和替换向量库。
真正的向量数组不保存在该表中。

### 4. 如何避免 LLM 无依据回答？

先按知识库过滤检索，使用最佳余弦距离与阈值判断依据是否充足；资料不足时不调用
聊天模型。Prompt 还要求只能依据编号资料回答，并将引用结构化返回。

### 5. 为什么检索要先扩大候选再去重？

直接对 Top-K 去重可能只剩少量结果。先召回更多候选，再按同一文档和规范化正文去重，
可以尽量补足最终 Top-K，同时减少重复引用。

### 6. SQLite 和 Chroma 如何保证一致性？

它们不能共享事务。SQLite 内部使用一次事务提交，Chroma 操作放在明确的顺序中；
如果 Chroma 写入后 SQLite 失败，就按本次 chroma_id 执行补偿删除。

### 7. 为什么重新切分要删除摘要和 FAQ？

摘要和 FAQ 都引用旧 Chunk。保留它们会让页面展示已经失效的引用，因此上游 Chunk
改变时必须让这些派生数据失效并重新生成。

### 8. 这算 Agent 项目吗？

算轻量工具路由 Agent。它具备目标输入、意图判断、工具选择、工具执行和步骤记录。
但它不是完整 ReAct Agent，因为没有多轮 Thought、Action、Observation 和自主反思循环。

### 9. 为什么 Router 不直接使用 LLM？

当前意图集合有限，规则方案确定、便宜且易测试。接口已经把 Router 输出定义为结构化
`AgentRouteDecision`，以后可以替换 LLM 分类，同时保留工具层。

### 10. Docker 和 GitHub Actions 有什么区别？

Docker 统一应用运行环境和启动方式；GitHub Actions 在代码推送后创建临时 Runner，
自动安装依赖并执行测试。一个解决怎么运行，一个解决怎么自动验收。

### 11. 项目中遇到过什么真实问题？

可以讲索引生命周期：原实现重新切分只替换 SQLite Chunk，旧 Chroma 向量可能继续被召回。
修复时不仅增加向量删除，还发现摘要、FAQ、外键和 ORM identity map 都需要一起处理，
最后用警告视为错误的测试验证没有隐藏的 SQLAlchemy 状态问题。

### 12. 下一步会怎么优化？

先扩充人工标注评估集，用已有指标验证 BM25 混合检索和 Rerank 是否真正改善召回；
再将数据层升级 PostgreSQL + pgvector，把文档处理迁移到后台任务队列，并增加登录与权限。

### 13. Hit Rate@K 和 MRR 有什么区别？

Hit Rate@K 只关心前 K 条里是否至少出现一个正确证据，适合衡量“有没有找回来”。
MRR 使用第一个正确证据排名的倒数，正确结果越靠前得分越高，适合衡量排序质量。

### 14. `/health` 和 `/health/ready` 为什么分开？

`/health` 只判断 FastAPI 进程能否响应；`/health/ready` 还检查 SQLite 和 Chroma。
容器仍存活但依赖不可用时，前者可以帮助诊断进程，后者告诉流量入口暂时不要分发请求。

### 15. 为什么上传文件要流式写入？

一次性 `read()` 会让大文件完整进入内存，并发上传时容易放大内存占用。分块读取让单次
写入占用可控，再配合大小限制和异常清理，避免超大文件与半成品文件长期占用磁盘。

### 16. 高频回答缓存怎样避免返回旧答案？

缓存只匹配同知识库、规范化后完全相同的问题，并把 Top-K、模型、检索阈值和 Prompt 哈希放入键中。
默认 TTL 是 1 小时；文档重新切分或建立新索引前会清空整个知识库缓存。当前不做语义相似缓存，
因为条件略有差异的问题可能需要不同答案。

TTL 只解决过期，不解决短时间高基数问题，所以系统还限制单知识库 500 条和全局 2000 条；超限时
按照最后命中时间或最近写入时间执行 LRU 批量淘汰。多实例高并发时再迁移 Redis。

## 6. 面试演示顺序

建议演示 5 到 8 分钟：

1. 打开 GitHub README，展示架构图和 CI 徽章。
2. 在 Streamlit 创建知识库并上传示例文档。
3. 展示 Chunk 切分和索引状态。
4. 提问一个有依据的问题，展开引用来源和 Agent 步骤。
5. 提问一个资料不足的问题，展示拒答边界。
6. 展示文档总结或多文档对比。
7. 打开 FastAPI `/docs` 和 GitHub Actions 结果。

不要把大部分时间花在创建按钮上，重点展示 RAG 数据流、引用和可观测信息。

## 7. 项目数据速记

面试前可以记住这些真实数字：

- 21 个 FastAPI API 操作
- 14 张 SQLAlchemy 业务表
- 4 类 Agent 意图
- 46 个 pytest 测试
- 2 个 Docker Compose 服务
- 3 类持久化位置：SQLite、Chroma、uploads
- 3 个检索评估指标：Hit Rate@K、MRR、关键词召回率
