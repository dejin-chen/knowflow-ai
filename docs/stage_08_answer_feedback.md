# 第八阶段：问答反馈

## 目标

让使用者对每条助手回答提交“有帮助”或“无帮助”反馈，形成问答质量闭环。

## 数据模型

`answer_feedbacks` 通过 `assistant_message_id` 关联一条助手消息，保存反馈类型、可选说明和创建时间。

当前项目尚未实现用户登录，因此每条助手消息只允许一条反馈。这样可以避免同一页面反复点击写入重复记录。后续接入用户体系后，可将唯一约束调整为 `(user_id, assistant_message_id)`。

## 数据流

```text
用户点击“有帮助”或“无帮助”
  -> POST /api/messages/{assistant_message_id}/feedback
  -> AnswerFeedbackService 校验目标确实是助手消息
  -> 写入 answer_feedbacks
  -> 历史消息接口返回 feedback 状态
```
