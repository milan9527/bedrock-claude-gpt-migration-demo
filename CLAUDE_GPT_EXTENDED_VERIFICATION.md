# Claude Converse → GPT HTTP API 扩展实测

2026-09-20，us-east-1，通过已部署应用执行。源端为 Bedrock Converse；
目标端分别为 Bedrock Runtime Chat Completions 和 Responses，未调用 Mantle。

实际模型组合：

- `us.anthropic.claude-opus-4-8` → `us.openai.gpt-5.6-sol`
- `us.anthropic.claude-fable-5-1` → `us.openai.gpt-6-astra`

HTTP 端点：

- `https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1/chat/completions`
- `https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1/responses`

## 九个扩展场景

多轮依赖工具调用（`agent_chain`）、并行工具（`agent_parallel`）、
工具失败后纠正（`agent_recovery`）、thinking 文本（`thinking`）、
thinking 加工具（`thinking_tools`）、文本流（`stream`）、
输出截断（`truncation`）、工具错误协议转换（`api_tool_error`）、
停止序列（`api_stop`）。

每个比较任务包含 Claude 源端、GPT 直接替换、GPT 适配后三个结果。
下表数值为“通过 / 调用错误”；所有任务均完成，无额外断言失败。
调用错误如实计入错误，未因为符合负向演示预期而改为通过。

| 目标 API | 目标模型 | Claude 源端 | GPT 直接替换 | GPT 适配后 |
| --- | --- | --- | --- | --- |
| Chat Completions | Sol | 7 / 2 | 3 / 6 | 8 / 1 |
| Chat Completions | Astra | 7 / 2 | 3 / 6 | 3 / 6 |
| Responses | Sol | 7 / 2 | 6 / 3 | 8 / 1 |
| Responses | Astra | 7 / 2 | 6 / 3 | 8 / 1 |

共 36 个比较任务、108 个结果：73 个通过、35 个调用错误。
原始证据：

- `.deploy/claude-converse-gpt-chat-extended.json`
- `.deploy/claude-converse-gpt-responses-extended.json`

## 实际兼容性结论

1. 两款 Claude 都拒绝旧的 `thinking.type=enabled`，服务端要求
   `thinking.type=adaptive` 和 `output_config.effort`。九场景测试中每组源端的
   两个 thinking 错误来自此参数，不能归因于 GPT 迁移。
2. Sol Chat 的五个工具场景直接替换均报 HTTP 400；服务端要求改用 Responses
   或设置 `reasoning_effort=none`。适配后使用 `none`，五个场景均通过。
   这会改变推理配置，不代表保留 Claude thinking 能力。
3. Astra Chat 的五个工具场景直接替换、适配后均报 HTTP 400；服务端建议使用
   Responses。本次没有静默切换 API，也没有将这些结果标成通过。
4. 两款 GPT 在 Responses 的五个适配后工具场景均通过，包括依赖参数传递、
   同轮并行调用、失败纠正和工具错误回传。
5. Responses 直接接收 Claude `thinking` 字段时返回 HTTP 400
   `Unknown parameter: 'thinking'`。适配后不传该字段，调用通过；
   这验证请求兼容性，不代表 Claude 与 GPT 推理行为等价。
6. 两款 GPT 的 Chat、Responses 均拒绝本次 `stop` 配置，直接替换与适配后
   都报 HTTP 400。停止序列迁移仍有明确缺口。
7. 文本流和主动触发输出上限的场景通过。截断通过仅表示正确识别
   `max_tokens`，答案仍不完整，不能当作业务任务完成。

## Adaptive thinking 补测

将源端改为以下参数，重复两个模型组合的 `thinking` 与 `thinking_tools`：

```json
{"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}
```

4 个比较任务、12 个结果：Claude 源端 4/4 通过，GPT 适配后 4/4 通过；
GPT 直接沿用 Claude 参数的 4 个结果全部返回 `Unknown parameter: 'thinking'`。
两个工具场景的源端和适配后均实际执行了查询工具。
证据：`.deploy/claude-converse-gpt-responses-adaptive.json`。

适配后 GPT 请求未传 Claude thinking 配置，也未显式指定 GPT reasoning 配置，
因此不能称为等价的推理模式迁移。Fable 本次两个源端结果均未记录可见 reasoning
block；参数被接受与返回可见推理内容是不同检查项。

包含此补测，本轮共 40 个比较任务、120 个结果：81 个通过、39 个调用错误，
没有额外断言失败。补测结果未覆盖或改写旧参数的失败证据。

## 覆盖边界

每个组合、场景仅运行一次，不构成稳定性或质量统计。thinking 文本检查只验证
非空输出和正常结束，不评分推理正确性。工具测试验证实际调用轨迹及指定断言，
不覆盖任意业务工具。流式测试只覆盖文本 SSE，不覆盖流式工具参数拼接。
Responses 使用 `store=false` 并回传历史 output items，未测试服务端会话管理。
这些结论仅适用于上述实际模型和 Runtime 端点，不推广到所有目录模型或 Mantle。

此前 Claude + Chat 的 404 复现与界面提示修复见
[404 复核报告](CHAT_COMPATIBILITY_VERIFICATION.md)。
本报告统计独立于 [既有 API 矩阵](API_MATRIX_VERIFICATION.md)，请勿重复累加。

## 复测

```bash
python3 deploy/verify_scenarios.py --source-api converse --target-api chat --scenarios agent_chain agent_parallel agent_recovery thinking thinking_tools stream truncation api_tool_error api_stop --output .deploy/claude-converse-gpt-chat-extended.json
python3 deploy/verify_scenarios.py --source-api converse --target-api responses --scenarios agent_chain agent_parallel agent_recovery thinking thinking_tools stream truncation api_tool_error api_stop --output .deploy/claude-converse-gpt-responses-extended.json
python3 deploy/verify_scenarios.py --source-api converse --target-api responses --adaptive --scenarios thinking thinking_tools --output .deploy/claude-converse-gpt-responses-adaptive.json
```
