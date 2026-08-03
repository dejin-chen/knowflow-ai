# 第八阶段：Token 用量记录

## 目标

记录每次真实 LLM 调用的输入、输出和总 Token，用于成本统计、性能分析和链路排查。

## 数据模型

`model_usage_logs` 关联 `assistant_message_id`，并记录：

- `operation`：调用场景，例如 `llm_rerank`、`knowledge_qa`、`document_summary`
- `model_name`：实际模型名称
- `prompt_tokens`：输入 Token
- `completion_tokens`：输出 Token
- `total_tokens`：总 Token

一条助手消息允许关联多条用量记录。这样以后即使一个 Agent 在同一轮中多次调用模型，也不需要修改表结构。

## 边界

只有真实调用 LLM 时才创建记录。一次普通问答可能先产生 `llm_rerank`，再产生 `knowledge_qa`；
资料不足时不调用回答模型，但已经发生的 Rerank 用量仍会记录。Router 规则判断和追问用户不产生模型用量。
