# 第十一阶段：轻量词法 Rerank

> 本文记录历史实现。当前默认策略已在第十二阶段升级为 LLM Rerank；本服务仍作为
> `lexical` 可选策略和模型故障时的自动降级方案。参见
> [第十二阶段文档](stage_12_llm_rerank.md)。

## 1. 为什么增加 Rerank

向量检索擅长找到语义相近内容，但“语义相近”不一定等于“最适合放在第一名”。企业制度问题经常
包含具体部门、期限、金额和材料名称，这些词法证据可以帮助重新排列已经召回的候选。

Rerank 不负责从整个知识库重新搜索。它只处理 Chroma 已经返回的 `top_k × 3` 个候选：

```text
问题 Embedding
→ Chroma 扩大召回候选
→ SQLite 回查正文并去重
→ 轻量 Rerank
→ 截取最终 Top-K
```

如果正确 Chunk 没有进入候选集，Rerank 无法把它凭空找回来。

## 2. 为什么不用大模型 Reranker

当前版本没有接入 Cross-Encoder 或 LLM Rerank，原因是：

- 不增加第二次模型调用、Token 和网络等待；
- 不引入 PyTorch、Sentence Transformers 等较大的运行依赖；
- 公式和排序过程适合应届生解释和编写确定性测试；
- 先用离线评估证明轻量方案是否有效，再决定是否增加模型复杂度。

因此简历和面试中应称为“轻量词法 Reranker”，不能说成训练过的深度学习排序模型。

## 3. 评分方法

问题和候选正文会提取两类特征：

- 连续中文文本提取双字片段，例如“设备遗失”得到“设备、备遗、遗失”；
- 英文和数字保留为完整词元，例如 `IT`、`VPN`、`20000`。

词法分数使用问题特征覆盖率：

```text
lexical_score = 问题与正文共有特征数 / 问题特征总数
semantic_score = clamp(1 - cosine_distance, 0, 1)
rerank_score = 0.5 × semantic_score + 0.5 × lexical_score
```

分数相同时保留原始向量顺序，避免没有词法信号时发生随机抖动。`rerank_score` 只用于同一次候选集
内部排序，不是概率，也不能跨问题比较。

## 4. 配置

```dotenv
RETRIEVAL_RERANK_ENABLED=true
RETRIEVAL_RERANK_LEXICAL_WEIGHT=0.5
```

关闭开关即可恢复纯向量排序。权重为 `0` 时只看向量，为 `1` 时只看词法。当前 `0.5` 是 30 题
开发集上的工程取舍，正式指标仍需使用未参与调参的独立测试集验证。

## 5. RAG 阈值和缓存变化

Rerank 后第一名不一定拥有最小 Chroma distance。资料不足判断因此使用最终候选中的最小原始向量
距离，而不是第一名的距离，更不能把 `rerank_score` 当作 distance。

回答缓存键增加 Rerank 开关和词法权重。配置变化后，同一个问题会得到新的缓存键，不会复用旧排序
生成的答案。

## 6. 评估方法

评估使用同一个本地 Docker 环境、同一个知识库、同一份员工手册、同一个 Embedding 模型和同一组
30 个人工标注问题。两轮都使用 Top-3，候选倍数为 3：

```text
第一轮：关闭 Rerank，保存纯向量基线
第二轮：开启 Rerank，其他配置保持不变
```

评估集位于 `evaluation/rerank_dataset.json`，逐题对比报告位于
`evaluation/reports/rerank_comparison_2026-08-03.json`。

在本地数据库准备好相同知识库后，可以分别运行：

```powershell
$env:RETRIEVAL_RERANK_ENABLED="false"
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --knowledge-base-id 6 `
  --dataset ..\evaluation\rerank_dataset.json `
  --output ..\evaluation\reports\rerank_baseline.json

$env:RETRIEVAL_RERANK_ENABLED="true"
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --knowledge-base-id 6 `
  --dataset ..\evaluation\rerank_dataset.json `
  --output ..\evaluation\reports\rerank_enabled.json
```

知识库 ID 以当前数据库为准。两轮运行前后不要重切分文档或更换 Embedding 模型。

## 7. 实测结果

| 指标 | 纯向量基线 | 轻量 Rerank | 绝对变化 | 相对增长 |
| --- | ---: | ---: | ---: | ---: |
| HitRate@3 | 0.8000 | 0.9667 | +16.67 个百分点 | +20.84% |
| MRR | 0.6167 | 0.9000 | +0.2833 | +45.94% |
| 关键词召回率 | 0.8000 | 0.9667 | +16.67 个百分点 | +20.84% |

“提升 16.67 个百分点”和“相对增长 20.84%”不是一回事。简历中使用百分点描述命中率变化更直观，
使用相对百分比时必须明确计算公式。

## 8. 失败样例

`training-expense-001` 在加入 Rerank 前后都没有命中。检查扩大召回候选后发现，包含“外部培训费用
需要提前申请”的正确证据没有进入候选集，所以排序器没有可提升的正确结果。

这个失败说明下一步应优化召回，例如：

- 调整 Chunk 边界，避免标题和关键句被切散；
- 加入 BM25 与向量混合召回；
- 扩大候选数量并评估延迟代价；
- 更换 Embedding 后使用同一评估集回归。

## 9. 关键文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/lightweight_rerank_service.py` | 提取词法特征并融合向量分数 |
| `backend/app/services/semantic_search_service.py` | 在去重后、Top-K 截断前调用 Reranker |
| `backend/app/core/config.py` | 管理开关与词法权重 |
| `backend/tests/test_stage_11_lightweight_rerank.py` | 验证候选提升、顺序稳定和功能开关 |
| `evaluation/rerank_dataset.json` | 30 题人工标注开发集 |
| `evaluation/reports/rerank_comparison_2026-08-03.json` | 前后逐题排名与汇总指标 |

## 10. 这一阶段学到了什么

- 召回负责“候选里有没有”，Rerank 负责“候选顺序是否合理”。
- Rerank 不能修复召回阶段完全漏掉的证据。
- 优化前后必须固定文档、模型、Top-K 和评估问题。
- 开发集可以选参数，最终简历指标应来自独立测试集。
- 任何提升都应保留失败样例和方案代价，而不是只展示总分。

## 11. 当前可用的简历表述

> 在 `top_k × 3` 向量候选上实现无额外模型调用的轻量词法 Reranker，融合 cosine distance 与中文
> 双字片段/英文词元覆盖率；在 30 题开发评估集上，HitRate@3 从 80.00% 提升至 96.67%，MRR 从
> 0.6167 提升至 0.9000。正式投递前将使用不少于 100 题的独立测试集复核。

该阶段当时只能明确写“30 题开发集”。第十二阶段已经使用分离的 100 题测试集完成 LLM Rerank
复核，正式简历指标应引用第十二阶段结果，不应混用两种排序方案的数据。
