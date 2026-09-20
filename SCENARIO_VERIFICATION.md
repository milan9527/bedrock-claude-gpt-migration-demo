# API 迁移场景验证报告

验证日期：2026-09-20。线上入口：https://d15ilm7z7pa2xp.cloudfront.net 。区域 us-east-1，调用 Bedrock Runtime；未接入 Mantle。

覆盖两个模型组合、18 个场景、两个跨 API 方向，每个用例含源模型/直接迁移/适配后三列，共 216 个结果：通过 180，未通过 4，API 错误 32。

Converse → InvokeModel 使用完整矩阵，并以最终版本的 12 个工具场景复测覆盖同名用例；其他用例沿用前一版本结果。InvokeModel → Converse 全部使用最终版本。Thinking 均显式设置源 Claude adaptive + medium effort。

## converse → invoke

### us.anthropic.claude-opus-4-8 → us.openai.gpt-5.6-sol

| 场景 | 源 Claude | 直接迁移 GPT | 适配后 GPT |
|---|---|---|---|
| summary | 通过 | 通过 | 通过 |
| extract | 未通过 | 通过 | 通过 |
| rag | 通过 | 通过 | 通过 |
| tools | 通过 | API 错误 | 通过 |
| agent_chain | 通过 | API 错误 | 通过 |
| agent_parallel | 通过 | API 错误 | 通过 |
| agent_recovery | 通过 | API 错误 | 通过 |
| thinking | 通过 | API 错误 | 通过 |
| thinking_tools | 通过 | API 错误 | 通过 |
| multiturn | 通过 | 通过 | 通过 |
| injection | 通过 | 通过 | 通过 |
| stream | 通过 | 通过 | 通过 |
| truncation | 通过 | 通过 | 通过 |
| api_unicode | 通过 | 通过 | 通过 |
| api_system | 通过 | 通过 | 通过 |
| api_history | 通过 | 通过 | 通过 |
| api_tool_error | 通过 | API 错误 | 通过 |
| api_stop | 通过 | API 错误 | API 错误 |

### us.anthropic.claude-fable-5-1 → us.openai.gpt-6-astra

| 场景 | 源 Claude | 直接迁移 GPT | 适配后 GPT |
|---|---|---|---|
| summary | 通过 | 通过 | 通过 |
| extract | 通过 | 通过 | 通过 |
| rag | 通过 | 通过 | 通过 |
| tools | 通过 | API 错误 | API 错误 |
| agent_chain | 通过 | API 错误 | API 错误 |
| agent_parallel | 通过 | API 错误 | API 错误 |
| agent_recovery | 通过 | API 错误 | API 错误 |
| thinking | 通过 | API 错误 | 通过 |
| thinking_tools | 通过 | API 错误 | API 错误 |
| multiturn | 通过 | 通过 | 通过 |
| injection | 通过 | 通过 | 通过 |
| stream | 通过 | 通过 | 通过 |
| truncation | 通过 | 通过 | 通过 |
| api_unicode | 未通过 | 通过 | 通过 |
| api_system | 通过 | 通过 | 通过 |
| api_history | 通过 | 通过 | 通过 |
| api_tool_error | 通过 | API 错误 | API 错误 |
| api_stop | 通过 | API 错误 | API 错误 |

## invoke → converse

### us.anthropic.claude-opus-4-8 → us.openai.gpt-5.6-sol

| 场景 | 源 Claude | 直接迁移 GPT | 适配后 GPT |
|---|---|---|---|
| summary | 通过 | 通过 | 通过 |
| extract | 未通过 | 通过 | 通过 |
| rag | 通过 | 通过 | 通过 |
| tools | 通过 | 通过 | 通过 |
| agent_chain | 通过 | 通过 | 通过 |
| agent_parallel | 通过 | 通过 | 通过 |
| agent_recovery | 通过 | 通过 | 通过 |
| thinking | 通过 | API 错误 | 通过 |
| thinking_tools | 通过 | API 错误 | 通过 |
| multiturn | 通过 | 通过 | 通过 |
| injection | 通过 | 通过 | 通过 |
| stream | 通过 | 通过 | 通过 |
| truncation | 通过 | 通过 | 通过 |
| api_unicode | 通过 | 通过 | 通过 |
| api_system | 通过 | 通过 | 通过 |
| api_history | 通过 | 通过 | 通过 |
| api_tool_error | 通过 | 通过 | 通过 |
| api_stop | 通过 | API 错误 | API 错误 |

### us.anthropic.claude-fable-5-1 → us.openai.gpt-6-astra

| 场景 | 源 Claude | 直接迁移 GPT | 适配后 GPT |
|---|---|---|---|
| summary | 通过 | 通过 | 通过 |
| extract | 通过 | 通过 | 通过 |
| rag | 通过 | 通过 | 通过 |
| tools | 通过 | 通过 | 通过 |
| agent_chain | 通过 | 通过 | 通过 |
| agent_parallel | 通过 | 通过 | 通过 |
| agent_recovery | 通过 | 通过 | 通过 |
| thinking | 通过 | API 错误 | 通过 |
| thinking_tools | 通过 | API 错误 | 通过 |
| multiturn | 通过 | 通过 | 通过 |
| injection | 通过 | 通过 | 通过 |
| stream | 通过 | 通过 | 通过 |
| truncation | 通过 | 通过 | 通过 |
| api_unicode | 未通过 | 通过 | 通过 |
| api_system | 通过 | 通过 | 通过 |
| api_history | 通过 | 通过 | 通过 |
| api_tool_error | 通过 | 通过 | 通过 |
| api_stop | 通过 | API 错误 | API 错误 |

## 解释与验收范围

- API 错误表示服务实际拒绝调用，不是业务场景通过。直接迁移保留 Claude 附加参数，GPT 拒绝专有 thinking/output_config 字段时保留原始错误。
- GPT 5.6 sol 原生 Chat Completions 工具调用：适配列未显式设置 reasoning_effort 时补入 none。这改变推理配置，不代表保留 Claude thinking 能力。用户显式参数不会被覆盖。
- GPT 6 Astra 原生 Chat Completions 当前工具与推理组合被服务拒绝；none 也不是该模型支持的取值，因此保留不兼容结果。
- 两种 GPT 的 InvokeModel 均拒绝 stop 参数，Converse 均拒绝 stopSequences；停止序列探针的服务错误保留展示。两种 GPT 经 Converse 的适配列均为 17/18 通过，剩余一项为停止序列。
- 截断场景故意限制为 32 tokens，检测 max_tokens 即通过；这不代表回答完整。其他场景截断仍不能算正常完成。
- 两个方向的 Opus 严格 JSON 未通过时均返回了 Markdown 围栏；未通过自动剥离来掩盖问题。前向矩阵 Fable 字符探针返回 content_filtered、空文本和零 token；反向矩阵返回 refusal 和空文本。不能把这些结果直接归因为编码转换错误。
- 工具/流式检查覆盖协议、轮次、部分格式及结束状态。每个用例是单次样例，不是稳定性、负载或完整语义质量评测。未逐个验证模型目录中的所有模型，也未验证所有 API 配对。
- 流式场景分别使用 ConverseStream / InvokeModelWithResponseStream，当前只覆盖文本事件；thinking 和工具往返使用非流式调用。

## 原始证据

- `.deploy/api-converse-invoke.json`：36 个用例，开始于 2026-09-20T09:40:02Z。
- `.deploy/api-converse-invoke-scope-fix.json`：12 个用例，开始于 2026-09-20T09:46:35Z。
- `.deploy/api-invoke-converse.json`：36 个用例，开始于 2026-09-20T09:48:21Z。
- 本地 16 项 unittest 通过，前端 JavaScript 语法检查通过。
