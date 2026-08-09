# 文档解析与文本切分

## 模块目标

文档处理模块将上传的 TXT / Markdown 原始文件转换为可检索文本块（Chunk），并写入 SQLite 的 `document_chunks` 表。

当前流程：

```text
documents.storage_path
  ↓
读取 TXT / Markdown 原始文件
  ↓
统一编码与清洗文本
  ↓
按 chunk_size 和 chunk_overlap 切分
  ↓
document_chunks 表
```

索引链路以 `document_chunks.content` 为输入生成 Embedding，并将向量写入 Chroma。

## 什么是 Chunk

Chunk 是从长文档中切出的、适合独立检索的小文本单元。不能直接对整篇文档做检索，原因包括：

- 整篇文档通常太长，Embedding 与 LLM 都有长度限制和成本。
- 文档太大时，检索结果粒度粗，难以精确命中答案所在段落。
- RAG 最终需要把少量相关片段放进 Prompt，而不是把所有资料放进去。

默认配置为：

- `CHUNK_SIZE=500`：每个 Chunk 最多约 500 个字符。
- `CHUNK_OVERLAP=80`：相邻 Chunk 保留约 80 个字符重叠。

重叠的意义是保留跨边界的上下文。例如一句话的条件在前一个 Chunk，结论在后一个 Chunk，没有 overlap 时可能把它们拆开。

## document_chunks 表

- `id`：Chunk ID
- `document_id`：来源文档 ID
- `knowledge_base_id`：所属知识库 ID
- `chunk_index`：该文档中的顺序编号，从 0 开始
- `content`：清洗后的 Chunk 正文
- `char_count`：字符数
- `start_offset` / `end_offset`：Chunk 在清洗后文本中的字符位置
- `created_at`：创建时间

`document_id + chunk_index` 有唯一约束，防止同一文档出现重复序号。

## 接口

```text
POST /api/documents/{document_id}/chunks
GET  /api/documents/{document_id}/chunks
```

第一个接口会解析并切分文档。重复执行时，系统会先删除旧的 chunks，再写入新的 chunks，因此不会累积重复数据。处理成功后，文档状态从 `uploaded` 更新为 `chunked`。

## 分层职责

- `DocumentParserService`：读取原始文件，处理 UTF-8 与 GB18030 编码。
- `TextSplitterService`：清洗文本，按自然边界和字符数切分。
- `DocumentChunkService`：编排解析、切分、保存的完整流程。
- `DocumentChunkRepository`：只负责 `document_chunks` 表的数据读写。
- `documents.py`：提供生成和查看 Chunk 的 HTTP 接口。

## 实现总结

- RAG 不是“上传文件后直接问大模型”，而是先把文档转成可检索的数据单元。
- Chunk 的大小影响检索精度和上下文完整性，overlap 用于减少边界信息丢失。
- Chunk 必须保存来源文档信息，才能在回答中提供引用溯源。
- 可重复执行的文档处理接口需要避免重复写入，这种设计叫幂等。

## 实现结果

> 实现 RAG 文档预处理链路：支持 TXT/Markdown 文档解析、文本清洗与可配置 Chunk 切分，将文本块及来源偏移持久化到 SQLite；通过覆盖式重建保证重复处理幂等，为后续向量索引和引用溯源提供数据基础。

## 关键设计决策

1. 为什么需要 Chunk overlap？

决策说明：文档语义可能跨越切分边界，保留少量重叠文本可避免条件与结论被完全拆开，提高召回片段的上下文完整性。

2. 为什么 Chunk 还要存 SQLite，不能只放向量库？

决策说明：SQLite 保存业务主数据、来源关系和可追溯内容，向量库专注相似度搜索。两者职责不同，向量存储可以替换，业务事实不依赖其内部结构。

3. 为什么同一文档重复切分时要替换旧数据？

决策说明：切分配置可能调整，替换旧 chunks 后写入新结果，可确保一个文档只有当前版本的切分结果，避免重复检索和脏数据。
