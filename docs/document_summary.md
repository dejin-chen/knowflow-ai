# 文档摘要生成

## 聊天总结与文档摘要的区别

聊天中的 `summarize_document` 是一次会话回答，会保存到 `messages`。文档摘要则是文档本身的长期属性，保存到 `document_summaries`，可在文档处理页随时查看。

## 数据流

```text
用户点击“生成摘要”
  -> POST /api/documents/{document_id}/summary
  -> 复用 AgentToolService 读取该文档 Chunk 并调用模型
  -> 保存摘要正文、引用、模型名和 Token 用量
  -> 再次生成时覆盖同一份文档的旧摘要
```

摘要不使用向量检索，因为目标文档已经由 `document_id` 明确指定。它要求文档至少完成 Chunk 切分；是否已建立向量索引不影响摘要生成。
