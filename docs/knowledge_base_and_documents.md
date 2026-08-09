# 知识库与文档管理

## 模块目标

本模块实现企业知识库的基础业务能力：

- 创建知识库
- 查看知识库列表
- 删除知识库
- 上传 TXT / Markdown 文档
- 保存文档元信息
- 查看某个知识库下的文档列表

该模块不解析文档正文，也不生成 Embedding，只负责管理资料入口与文档元信息。

## 为什么先做知识库和文档管理

RAG 系统不是直接把文件丢给大模型。

正式流程通常是：

```text
知识库
  ↓
文档
  ↓
文本解析
  ↓
Chunk 切分
  ↓
Embedding
  ↓
向量检索
  ↓
LLM 生成回答
```

本模块解决前两步：资料归属和文档元信息。

## 两张数据库表

`knowledge_bases` 表保存知识库：

- `id`：知识库 ID
- `name`：知识库名称
- `description`：知识库说明
- `created_at`：创建时间
- `updated_at`：更新时间

`documents` 表保存文档元信息：

- `id`：文档 ID
- `knowledge_base_id`：所属知识库 ID
- `filename`：原始文件名
- `file_type`：文件类型，例如 `txt`、`md`
- `file_size`：文件大小
- `storage_path`：服务器本地保存路径
- `status`：文档状态，当前为 `uploaded`
- `created_at`：上传时间

## 分层设计

`Model`：定义数据库表。

`Schema`：定义 API 输入输出结构。

`Repository`：负责数据库读写。

`Service`：负责业务规则，例如判断知识库是否存在、校验文件类型、保存上传文件。

`API`：负责接收 HTTP 请求，把请求交给 Service。

这种拆分可以避免把所有逻辑都写在接口函数里。

## 当前 API

```text
POST   /api/knowledge-bases
GET    /api/knowledge-bases
DELETE /api/knowledge-bases/{knowledge_base_id}
POST   /api/knowledge-bases/{knowledge_base_id}/documents
GET    /api/knowledge-bases/{knowledge_base_id}/documents
```

## 实现总结

- 一个正式项目中，数据库表、接口结构、业务逻辑、数据访问应该分层。
- 文件上传不能直接信任用户文件名，需要生成服务器内部文件名。
- 文档元信息和文档正文不是一回事，后续 Chunk 和 Embedding 会基于元信息找到原始文件。
- 删除知识库时，要考虑它下面的文档如何处理。

## 实现结果

交付结果：

> 设计并实现知识库与文档管理模块，基于 FastAPI、SQLAlchemy 完成知识库 CRUD、TXT/Markdown 文档上传、文档元信息持久化和分层业务结构，为后续文档解析、Chunk 切分和向量索引构建提供稳定数据入口。

## 关键设计决策

1. 为什么文档表只保存 storage_path，不直接保存全文？

决策说明：原始文件可能较大，直接存入数据库不利于管理。系统先保存文件路径和元信息，再由解析服务读取文件并生成 chunks，以保持处理职责分离。

2. 为什么要有 Service 和 Repository？

决策说明：Service 承载业务规则，Repository 封装数据库读写，使接口保持轻量，并支持 API、测试和后台任务复用业务逻辑。

3. 上传文件时为什么要重命名？

决策说明：用户文件名可能重复或包含路径字符，服务器内部使用 UUID 命名可避免覆盖和路径穿越风险。
