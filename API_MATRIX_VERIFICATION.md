# 多场景、多 API 线上验证

测试日期：2026-09-20。区域：us-east-1。
线上入口：https://d15ilm7z7pa2xp.cloudfront.net 。通过登录后的应用 API 发起真实模型调用。
四种模型 API 均使用 Bedrock Runtime；本报告未测试 Mantle。

已记录 78 个比较任务、234 个结果，覆盖 16 种 API 前后组合、18 个场景、4 个模型。
断言通过 208；调用错误 24；断言未通过 2；未完整结束的任务 0。
每个任务分别执行源模型、直接迁移目标、适配迁移目标。不同组合使用的模型见下表及私有原始证据，本轮并非所有模型 × 所有 API × 所有场景的笛卡尔积。

## 分组结果

各结果列依次为 **通过 / 调用错误 / 断言未通过**。

| 分组（源 API → 目标 API） | 任务数 | 源模型 | 直接迁移 | 适配迁移 |
|---|---:|---:|---:|---:|
| chat-chat | 3 | 2/1/0 | 2/1/0 | 3/0/0 |
| chat-converse | 3 | 2/1/0 | 3/0/0 | 3/0/0 |
| chat-invoke | 3 | 2/1/0 | 2/1/0 | 3/0/0 |
| chat-responses | 3 | 2/1/0 | 3/0/0 | 3/0/0 |
| converse-chat | 3 | 3/0/0 | 2/1/0 | 2/1/0 |
| converse-converse | 3 | 3/0/0 | 3/0/0 | 3/0/0 |
| converse-invoke | 3 | 3/0/0 | 2/1/0 | 2/1/0 |
| converse-responses | 3 | 3/0/0 | 3/0/0 | 3/0/0 |
| extended-fable-astra | 15 | 14/0/1 | 12/3/0 | 14/1/0 |
| extended-opus-sol | 15 | 14/0/1 | 12/3/0 | 14/1/0 |
| invoke-chat | 3 | 3/0/0 | 2/1/0 | 3/0/0 |
| invoke-converse | 3 | 3/0/0 | 3/0/0 | 3/0/0 |
| invoke-invoke | 3 | 3/0/0 | 2/1/0 | 3/0/0 |
| invoke-responses | 3 | 3/0/0 | 3/0/0 | 3/0/0 |
| responses-chat | 3 | 3/0/0 | 2/1/0 | 2/1/0 |
| responses-converse | 3 | 3/0/0 | 3/0/0 | 3/0/0 |
| responses-invoke | 3 | 3/0/0 | 2/1/0 | 2/1/0 |
| responses-responses | 3 | 3/0/0 | 3/0/0 | 3/0/0 |

`extended-*` 使用 InvokeModel → Responses，覆盖主矩阵之外的 15 个场景。
主矩阵覆盖摘要、多步 Agent、文本流；扩展场景覆盖 JSON、RAG、工具、并行、错误恢复、thinking、thinking+tools、多轮对话、注入、截断、Unicode、系统优先级、历史更正、工具错误协议和停止序列。

## 各组合实际使用的模型

Responses 和 Chat Completions 的源端使用 GPT，用于验证 API 间迁移；本轮未将 Claude 接入这两种 API，也不能据此推断其支持情况。

| 分组 | 源模型 | 目标模型 |
|---|---|---|
| chat-chat | `us.openai.gpt-6-astra` | `us.openai.gpt-5.6-sol` |
| chat-converse | `us.openai.gpt-5.6-sol` | `us.openai.gpt-6-astra` |
| chat-invoke | `us.openai.gpt-6-astra` | `us.openai.gpt-5.6-sol` |
| chat-responses | `us.openai.gpt-5.6-sol` | `us.openai.gpt-6-astra` |
| converse-chat | `us.anthropic.claude-fable-5-1` | `us.openai.gpt-6-astra` |
| converse-converse | `us.anthropic.claude-opus-4-8` | `us.openai.gpt-5.6-sol` |
| converse-invoke | `us.anthropic.claude-fable-5-1` | `us.openai.gpt-6-astra` |
| converse-responses | `us.anthropic.claude-opus-4-8` | `us.openai.gpt-5.6-sol` |
| extended-fable-astra | `us.anthropic.claude-fable-5-1` | `us.openai.gpt-6-astra` |
| extended-opus-sol | `us.anthropic.claude-opus-4-8` | `us.openai.gpt-5.6-sol` |
| invoke-chat | `us.anthropic.claude-opus-4-8` | `us.openai.gpt-5.6-sol` |
| invoke-converse | `us.anthropic.claude-fable-5-1` | `us.openai.gpt-6-astra` |
| invoke-invoke | `us.anthropic.claude-opus-4-8` | `us.openai.gpt-5.6-sol` |
| invoke-responses | `us.anthropic.claude-fable-5-1` | `us.openai.gpt-6-astra` |
| responses-chat | `us.openai.gpt-5.6-sol` | `us.openai.gpt-6-astra` |
| responses-converse | `us.openai.gpt-6-astra` | `us.openai.gpt-5.6-sol` |
| responses-invoke | `us.openai.gpt-5.6-sol` | `us.openai.gpt-6-astra` |
| responses-responses | `us.openai.gpt-6-astra` | `us.openai.gpt-5.6-sol` |

## 未通过结果（保留真实错误）

### us.anthropic.claude-fable-5-1 / invoke / failed（1 次）

```text
Unicode、引号、反斜杠往返一致；完整结束（end_turn）
stopReason: refusal
实际输出: ""
```

涉及：extended-fable-astra/api_unicode/源模型

### us.anthropic.claude-opus-4-8 / invoke / failed（1 次）

```text
JSON 与字段类型
stopReason: end_turn
实际输出: "```json\n{\n  \"order_id\": \"A100\",\n  \"total\": 299,\n  \"shipping_refund\": 15,\n  \"refund_approved\": false\n}\n```"
```

涉及：extended-opus-sol/extract/源模型

### us.openai.gpt-5.6-sol / chat / error（4 次）

```text
Bedrock chat HTTP 400: {"error":{"message":"Function tools with reasoning_effort are not supported for us.openai.gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.","type":"invalid_request_error","param":"reasoning_effort","code":"validation_error"}}
```

涉及：chat-chat/agent_chain/直接迁移、chat-converse/agent_chain/源模型、chat-responses/agent_chain/源模型、invoke-chat/agent_chain/直接迁移

### us.openai.gpt-5.6-sol / invoke / error（2 次）

```text
An error occurred (ValidationException) when calling the InvokeModel operation: {"error":{"code":"validation_error","message":"Function tools with reasoning_effort are not supported for us.openai.gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.","param":"reasoning_effort","type":"invalid_request_error"}}
```

涉及：chat-invoke/agent_chain/直接迁移、invoke-invoke/agent_chain/直接迁移

### us.openai.gpt-5.6-sol / responses / error（2 次）

```text
Bedrock responses HTTP 400: {"error":{"message":"Unknown parameter: 'stop'.","type":"invalid_request_error","param":"stop","code":"unknown_parameter"}}
```

涉及：extended-opus-sol/api_stop/直接迁移、extended-opus-sol/api_stop/适配迁移

### us.openai.gpt-5.6-sol / responses / error（2 次）

```text
Bedrock responses HTTP 400: {"error":{"message":"Unknown parameter: 'thinking'.","type":"invalid_request_error","param":"thinking","code":"unknown_parameter"}}
```

涉及：extended-opus-sol/thinking/直接迁移、extended-opus-sol/thinking_tools/直接迁移

### us.openai.gpt-6-astra / chat / error（6 次）

```text
Bedrock chat HTTP 400: {"error":{"message":"Function tools with reasoning_effort are not supported for us.openai.gpt-6-astra in /v1/chat/completions. To use function tools, use /v1/responses.","type":"invalid_request_error","param":"reasoning_effort","code":"validation_error"}}
```

涉及：chat-chat/agent_chain/源模型、chat-invoke/agent_chain/源模型、converse-chat/agent_chain/直接迁移、converse-chat/agent_chain/适配迁移、responses-chat/agent_chain/直接迁移、responses-chat/agent_chain/适配迁移

### us.openai.gpt-6-astra / invoke / error（4 次）

```text
An error occurred (ValidationException) when calling the InvokeModel operation: {"error":{"code":"validation_error","message":"Function tools with reasoning_effort are not supported for us.openai.gpt-6-astra in /v1/chat/completions. To use function tools, use /v1/responses.","param":"reasoning_effort","type":"invalid_request_error"}}
```

涉及：converse-invoke/agent_chain/直接迁移、converse-invoke/agent_chain/适配迁移、responses-invoke/agent_chain/直接迁移、responses-invoke/agent_chain/适配迁移

### us.openai.gpt-6-astra / responses / error（2 次）

```text
Bedrock responses HTTP 400: {"error":{"message":"Unknown parameter: 'stop'.","type":"invalid_request_error","param":"stop","code":"unknown_parameter"}}
```

涉及：extended-fable-astra/api_stop/直接迁移、extended-fable-astra/api_stop/适配迁移

### us.openai.gpt-6-astra / responses / error（2 次）

```text
Bedrock responses HTTP 400: {"error":{"message":"Unknown parameter: 'thinking'.","type":"invalid_request_error","param":"thinking","code":"unknown_parameter"}}
```

涉及：extended-fable-astra/thinking/直接迁移、extended-fable-astra/thinking_tools/直接迁移

## 迁移结论

- GPT 5.6 Sol 的 Chat Completions 工具调用需要适配推理参数；本轮适配列使用 `reasoning_effort=none`。InvokeModel 使用相同原生协议时也受到该约束。
- GPT 6 Astra 在本轮 Chat Completions 工具配置下被服务拒绝；服务提示改用 Responses。报告保留错误，应用不会自动切换 API。
- Claude 专有 `thinking` 参数不能直接传入 GPT Responses。移除字段后调用通过，只证明请求兼容，不证明推理能力等价。
- Responses 拒绝停止序列参数；直接迁移和适配迁移均保留这一错误。
- JSON 抽取按严格 JSON 文本解析；Markdown 代码围栏也会导致失败，不能仅凭字段看起来正确就标记通过。

## 判定边界与复现

- 截断场景故意限制输出，识别 `max_tokens` 即检测通过，回答仍然不完整。
- 摘要等场景只检查有文本和正常结束；RAG 只检查引用格式，不代表语义质量全部正确。
- 并行工具的“同轮请求”是观察项；本报告严格统计全部断言，观察项为假也计入断言未通过。
- Claude thinking 参数随直接迁移请求传入 GPT；若被服务拒绝，记录为调用错误，不能算迁移成功。
- 工具来自演示的确定性业务函数；流式测试覆盖文本 SSE，不覆盖工具参数增量。
- 未覆盖浏览器自动化、负载、限流、长时间稳定性、图像/音频、服务端 Responses 会话持久化。

原始结果位于 `.deploy/expanded-api-matrix/*.json`，包含实际模型、API、端点、工具轨迹、各轮 usage、停止原因和断言；文件为本地私有证据。

```bash
python3 deploy/verify_api_matrix.py
python3 deploy/summarize_api_matrix.py
```

测试器串行运行，避免应用同一时间只允许一个比较任务的限制。已完整记录的分组会跳过；如需全新复测，请先归档现有证据目录。
