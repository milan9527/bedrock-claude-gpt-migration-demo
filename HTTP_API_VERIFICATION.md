# Responses / Chat Completions 验证

验证日期：2026-09-20，区域：us-east-1。

新增 API 使用 Bedrock Runtime HTTP endpoint，通过 ECS task role / SigV4 认证：

- Responses：`/openai/v1/responses`
- Chat Completions：`/openai/v1/chat/completions`

迁移前、迁移后分别可以选择 Converse、InvokeModel、Responses、Chat Completions。模型来自账户模型目录；选择器不代表每个模型都支持每个 API。不支持的组合保留服务错误，不自动切换 API。

## 真实模型测试

本地 Workbench 调用真实 AWS endpoint，覆盖两个 GPT 模型、两个新增 API、全部 18 个场景，共 72 次。测试使用适配后的提示词及参数，**不代表直接迁移列全部通过**。

| 模型 | API | 检查通过 | 服务错误 |
|---|---|---:|---:|
| GPT-5.6 Sol | Responses | 17 | 1 |
| GPT-5.6 Sol | Chat Completions | 17 | 1 |
| GPT-6 Astra | Responses | 17 | 1 |
| GPT-6 Astra | Chat Completions | 11 | 7 |
| 合计 | | 62 | 10 |

原始证据：`.deploy/http-api-matrix.json`（本地私有文件）。

10 个服务错误：

- 四个模型/API 组合均拒绝 `stop`。Responses 返回 unknown parameter；Chat Completions 返回 unsupported parameter。停止序列兼容场景保留错误。
- GPT-6 Astra 的 Chat Completions 在本次参数配置下拒绝六个工具场景：单次工具、多步 Agent、并行工具、工具恢复、thinking+tools、工具错误协议。服务明确建议使用 Responses。
- GPT-5.6 Sol 的 Chat Completions 工具场景在适配列使用 `reasoning_effort: none`。

通过项包含文本、JSON、RAG、多轮历史、Unicode、系统消息、文本流以及输出截断检测。截断场景“通过”表示正确识别输出上限，不表示答案完整。Agent 及工具场景通过情况取决于上述模型/API 支持范围。

## 适配与验证边界

- Responses 使用 `instructions`、`input`、`max_output_tokens`，工具调用按 `call_id` 对应 `function_call_output`；客户端保留响应 output 条目用于后续工具轮次。
- Chat Completions 使用 `messages`、`max_completion_tokens`，工具结果按 `tool_call_id` 回传。
- 两种 API 均处理文本 SSE、终止原因和 usage；流场景尚不覆盖工具参数增量。
- Responses 使用 `store: false`，未实现服务端 `previous_response_id` 会话管理。
- 21 项本地测试通过，包含协议转换、工具关联与 reasoning 条目回传、SSE 截断与错误、请求字段保护，以及既有应用测试。
- 自动检查验证具体场景断言，不是完整的安全评估或模型质量评估；API 参数兼容错误不能算作成功调用。

## 部署后验证

线上地址：https://d15ilm7z7pa2xp.cloudfront.net 。已通过登录后的 HTTP 检查确认目录返回四种 API、18 个场景，前端包含两个独立 API 选择器。未进行浏览器交互自动化。

- Converse → Responses：两个 Claude/GPT 演示模型对分别执行摘要、多步 Agent、thinking+tools、文本流、截断，共 30 个结果。首次检查 27 个通过，两个直接迁移结果拒绝 Claude `thinking` 参数，一个适配结果出现 IAM 401。
- ECS task role 已补充 `project/default` 的模型调用权限，部署脚本同步修复。上述 IAM 401 对应的 GPT-6 Astra thinking+tools 已重新执行：源模型、适配后目标均通过；直接迁移仍按服务行为返回 `thinking` 参数错误。原始失败记录保留，不计为通过。
- Chat Completions → Responses、Responses → Chat Completions：分别执行摘要和文本流，每个场景三列，共 12 个结果全部通过。
- 截断场景所有列均识别为 `max_tokens`，检查通过；这表示检测到了预期截断。

部署验证证据：`.deploy/live-converse-responses.json`、`.deploy/live-thinking-recheck.json`、`.deploy/live-chat-responses.json`、`.deploy/live-responses-chat.json`，均为本地私有文件。
