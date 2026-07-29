# 第八阶段：Token 用量记录

## 目标

记录每次真实 LLM 调用的输入、输出和总 Token，用于成本统计、性能分析和链路排查。

## 数据模型

`model_usage_logs` 关联 `assistant_message_id`，并记录：

- `operation`：调用场景，例如 `knowledge_qa`、`document_summary`
- `model_name`：实际模型名称
- `prompt_tokens`：输入 Token
- `completion_tokens`：输出 Token
- `total_tokens`：总 Token

一条助手消息允许关联多条用量记录。这样以后即使一个 Agent 在同一轮中多次调用模型，也不需要修改表结构。

## 边界

只有真实调用 LLM 时才创建记录。资料不足直接返回固定答案、Router 规则判断、追问用户等路径不消耗聊天模型 Token，因此不会产生用量日志。
