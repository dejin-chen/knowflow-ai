# LLM Rerank 与 100 题独立评测

> 本文保留“纯向量候选 + LLM Rerank”的历史基线。当前默认检索链路已升级为
> [BM25 + RRF 混合召回](hybrid_retrieval.md)，候选命中率和最终排序指标以混合检索报告为准。

## 1. 排序问题与目标

Chroma 负责快速找出语义相近的候选，但原始向量距离不一定能把最适合回答问题的片段排在前面。
LLM Rerank 不重新搜索整个知识库，而是阅读问题和少量候选，重新决定候选顺序：

```text
问题 Embedding
→ Chroma 扩大召回
→ SQLite 回查正文并去重
→ LLM 对已有 chunk_id 排序
→ 截取 Top-K
→ 构造 RAG Prompt 并生成回答
```

召回解决“正确证据有没有进入候选集”，Rerank 解决“候选顺序是否合理”。如果正确证据没有被
Chroma 召回，LLM Rerank 也不能凭空创建它。

## 2. 为什么使用结构化编号输出

Reranker 的输入为用户问题和最多 12 个候选，每个候选包含 `chunk_id`、文件名、Chunk 序号和正文。
Prompt 要求模型只输出：

```json
{"ranked_chunk_ids": [17, 12, 19]}
```

模型可以省略低相关候选，程序会按原向量顺序追加；但重复编号、未知编号、空数组和非法 JSON
不会被信任。这样 LLM 只拥有“排序权”，没有“创造证据权”。

## 3. 失败降级

LLM Rerank 增加了外部依赖，不能让它的故障阻断整个问答链路。以下情况会自动降级到词法排序：

- 模型超时、连接失败或接口错误；
- 返回内容不是合法 JSON；
- 返回重复、未知或空的候选编号。

词法降级融合 Chroma 距离与中文双字片段/英文词元覆盖率。降级结果的 `rerank_method` 为
`lexical_fallback`，正常结果为 `llm`。即使 JSON 解析失败，只要模型调用已经完成，系统仍记录
这次调用消耗的 Token；接口调用本身失败、没有用量时才不记录。

## 4. Token 与缓存怎样流转

一次未命中缓存的知识问答通常有两笔模型用量：

1. `llm_rerank`：对候选片段排序；
2. `knowledge_qa`：基于最终 Top-K 生成回答。

两笔记录都关联同一个助手消息并保存到 `model_usage_logs`，Streamlit 的“模型用量”区域会区分
“候选重排”和“问答生成”。回答缓存的成本字段也会累加两笔用量；缓存命中后同时跳过 Embedding、
LLM Rerank 和回答生成。

缓存键包含 Rerank 策略、模型、候选上限、正文截断长度和 Prompt 版本。更换排序策略后，旧排序
产生的回答不会被错误复用。

## 5. 配置

```dotenv
RETRIEVAL_RERANK_ENABLED=true
RETRIEVAL_RERANK_STRATEGY=llm
RETRIEVAL_RERANK_MODEL=
RETRIEVAL_RERANK_MAX_CANDIDATES=12
RETRIEVAL_RERANK_MAX_CHUNK_CHARACTERS=800
RETRIEVAL_RERANK_LEXICAL_WEIGHT=0.5
```

`RETRIEVAL_RERANK_MODEL` 留空时复用 `CHAT_MODEL`。把策略改成 `lexical` 可以主动使用本地词法排序；
关闭开关则恢复纯向量顺序。

## 6. 评测设计

- 开发集：原有 30 题，用于开发轻量词法排序；
- 独立测试集：新增 100 个未用于词法权重调节的问题，人工标注预期文件与事实关键词；
- 固定项：同一知识库、同一文档、同一 Embedding 模型、同一候选集、Top-3；
- 唯一变量：原始向量顺序与 LLM 排序；
- 指标：HitRate@3、MRR、关键词召回率、候选命中率、Token、平均延迟、P95 延迟和降级次数。

脚本先批量生成 100 个问题向量，每道题只召回一次候选，再让基线与 LLM 共用候选，避免两轮
Embedding 调用差异影响对比。

```powershell
docker cp evaluation\rerank_test_dataset.json `
  knowflow-ai-backend-1:/tmp/rerank_test_dataset.json

docker exec knowflow-ai-backend-1 python scripts/benchmark_llm_rerank.py `
  --knowledge-base-id 6 `
  --dataset /tmp/rerank_test_dataset.json `
  --output /tmp/llm_rerank_report.json
```

知识库 ID 以本机数据库为准。评测会产生真实模型费用，不应在 CI 中自动运行。

## 7. 实测结果

模型配置为 `text-embedding-v2` 与 `deepseek-chat`，候选上限为 12：

| 指标 | 纯向量基线 | LLM Rerank | 变化 |
| --- | ---: | ---: | ---: |
| HitRate@3 | 0.82 | 0.94 | +12 个百分点，相对 +14.63% |
| MRR | 0.56 | 0.94 | 相对 +67.86% |
| 关键词召回率 | 0.8008 | 0.94 | 相对 +17.38% |

成本与稳定性：

| 指标 | 结果 |
| --- | ---: |
| 候选命中率 | 0.95 |
| 平均 Rerank Token | 2634.15 |
| 总 Rerank Token | 263415 |
| 平均 Rerank 延迟 | 3221.44 ms |
| P95 Rerank 延迟 | 5713.15 ms |
| 词法降级 | 1 / 100 |

完整逐题报告位于 `evaluation/reports/llm_rerank_comparison_2026-08-03.json`。

## 8. 怎样理解失败样例

- 5 题的正确证据没有进入 12 个候选，说明下一步应优化召回，例如 BM25 + RRF、Chunk 边界或
  Embedding，而不是继续修改 Rerank Prompt；
- `principle-record-103` 的正确证据已经进入候选，但 LLM 没有排入 Top-3，是一次真正的排序失误；
- `scope-collaborator-102` 返回空编号并触发词法降级，同时该题本身也未召回正确证据。

候选命中率 95% 是当前 Rerank 的理论上限；最终 HitRate@3 为 94%，说明 LLM 找回了大部分可用
候选，但并非绝对正确。

这 100 题来自同一份模拟员工手册，能够验证本项目内的回归效果，不能直接宣称对所有企业文档都
达到 94% 准确率。

## 9. 关键文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/llm_rerank_service.py` | Prompt、JSON 校验、排序与词法降级 |
| `backend/app/services/semantic_search_service.py` | 扩大召回、同候选排序和重排元数据 |
| `backend/app/services/rag_chat_service.py` | 将重排用量传入问答结果和缓存成本 |
| `backend/app/services/agent_chat_service.py` | 分别持久化重排与回答 Token |
| `backend/scripts/benchmark_llm_rerank.py` | 同候选质量、Token 和延迟对比 |
| `backend/tests/test_llm_rerank.py` | 验证合法排序、部分编号和失败降级 |
| `evaluation/rerank_test_dataset.json` | 100 题人工标注独立测试集 |

## 10. 实现总结

- Rerank 是候选排序，不是重新召回，也不是答案生成；
- LLM 结构化输出仍需白名单、去重和完整性校验；
- 降级路径必须可观察，解析失败也可能已经产生 Token 成本；
- 离线效果要与延迟、Token、失败率一起评估；
- 同候选对比才能把排序收益与 Embedding 波动分开。

## 11. 实现结果

> 在最多 12 个向量候选上实现结构化 LLM Rerank，通过 chunk_id 白名单与 JSON 校验限制模型仅执行
> 排序，并在超时或非法输出时自动降级为词法排序；在 100 题独立测试集上将 HitRate@3 从 82%
> 提升至 94%、MRR 从 0.56 提升至 0.94，同时记录平均 2634 Token、3.22 秒延迟及 1% 降级率。

## 12. 关键设计决策

- 候选先精排再进入回答模型，避免无关上下文稀释证据并增加生成成本。
- 未知 `chunk_id` 违反候选白名单合同，整次模型排序必须判为无效并降级，不能部分采信。
- 解析失败不代表模型未执行；Token 仍需计入成本与失败监控。
- HitRate@3 提升而候选命中率不变，说明收益来自候选排序，而不是召回覆盖率。
- BM25 补充字面命中，RRF 在不直接混合不同分数量纲的前提下融合关键词与向量排名。
- 默认启用 LLM Rerank 以获得质量收益，同时保留词法降级保证可用性，并用回答缓存减少重复调用成本。
