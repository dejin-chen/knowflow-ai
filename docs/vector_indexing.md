# Embedding 与 Chroma 向量索引

## 模块目标

文档处理链路已经把原始文档切成 `document_chunks`。索引模块为每个 Chunk 建立语义索引，并支持在指定知识库范围内按语义检索。

```text
SQLite: document_chunks.content
  ↓
Embedding API
  ↓
向量数组 embedding
  ↓
Chroma: id + embedding + document + metadata
  ↓
SQLite: vector_indexes 映射记录
```

## 什么是 Embedding

Embedding 是模型把一句文本转换成一串浮点数的过程。例如：

```text
"病假需要提供证明材料"
  ↓
[0.018, -0.231, 0.704, ...]
```

这串数字不是给人阅读的，而是为了比较语义距离。语义相近的句子，向量距离通常也更近。

## Chroma 保存什么

以 `document_chunks.id = 101` 为例，Chroma 保存一条记录：

```text
id: "chunk-101"
embedding: [0.018, -0.231, 0.704, ...]
document: "病假需要提供证明材料"
metadata:
  chunk_id: 101
  document_id: 12
  knowledge_base_id: 3
  chunk_index: 2
```

只有 `document` 的文本内容参与 Embedding。`metadata` 不参与语义计算，它用于按知识库过滤和检索后的引用溯源。

## 为什么还要 vector_indexes 表

Chroma 不承担项目的业务主数据管理。本项目新增 `vector_indexes` 表记录：

- `chunk_id`：SQLite Chunk ID
- `chroma_id`：Chroma 内部 ID，例如 `chunk-101`
- `status`：索引状态
- `indexed_at`：建立索引时间
- `last_error`：预留给失败信息

这样更换向量库或重建索引时，业务数据库仍然能够追踪每个 Chunk 的索引状态。

## 建索引接口

```text
POST /api/documents/{document_id}/index
```

调用该接口的前提是文档已经完成 Chunk 切分。它会：

1. 查询文档的所有 chunks。
2. 将所有 `content` 批量发送给 Embedding API。
3. 将向量、正文和 metadata 写入 Chroma。
4. 写入 `vector_indexes` 映射。
5. 将文档状态更新为 `indexed`。

## 实现结果

> 设计 RAG 向量索引模块，基于 OpenAI 兼容 Embedding API 与 Chroma 为文档 Chunk 构建持久化语义索引；通过 metadata 保存知识库、文档和 Chunk 标识，并以 SQLite 映射表管理索引状态，为后续知识库范围检索和引用溯源提供基础。

## 语义检索接口

```text
POST /api/knowledge-bases/{knowledge_base_id}/search
```

请求示例：

```json
{
  "query": "病假需要什么材料？",
  "top_k": 3
}
```

检索流程：

```text
用户问题
  ↓ Embedding
问题向量
  ↓ Chroma（where knowledge_base_id）
Top-K metadata + distance
  ↓ SQLite（按 chunk_id 批量回查）
Chunk 正文 + 文件名 + 来源信息
```

返回的 `distance` 是余弦距离，数值越小通常表示语义越相近。接口原样返回距离，不将其包装成容易误解的“百分比相似度”。

## 实现总结

- Embedding 解决的是“文本如何被数字化表示”，不是直接生成答案。
- Chroma 的 `embedding` 用于相似度计算，`metadata` 用于知识库过滤和溯源。
- SQLite 和 Chroma 职责不同：前者保存业务事实，后者保存语义索引。
- 建索引应使用批处理，降低 API 网络调用次数。
- 检索结果要用 `chunk_id` 回查业务数据库，才能返回可靠的引用来源。

## 关键设计决策

1. 为什么检索后还要查询 SQLite？

决策说明：Chroma 擅长按向量距离排序，SQLite 保存完整业务关系和文档元信息。通过 `chunk_id` 回查可取得权威正文、文件名和来源，避免向量库成为业务事实的唯一来源。

2. 如何避免不同知识库的资料混在一起？

决策说明：写入 Chroma 时将 `knowledge_base_id` 放入 metadata，查询时使用 `where` 过滤，使向量相似度只在指定知识库范围内比较。
