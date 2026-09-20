# Runtime Chat Completions 404 复核

2026-09-20，us-east-1，实际部署应用调用 Bedrock Runtime
`https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1/chat/completions`。

摘要场景、源端与目标端均选 Chat Completions：

| 模型 | 结果 |
| --- | --- |
| `us.anthropic.claude-opus-4-8` | HTTP 404 / `model_not_found` |
| `us.anthropic.claude-fable-5-1` | HTTP 404 / `model_not_found` |
| `us.openai.gpt-5.6-sol` | 直接替换、适配两组均正常结束 |
| `us.openai.gpt-6-astra` | 直接替换、适配两组均正常结束 |

原始证据：`.deploy/chat-404-reproduction.json`。
将源端改为 Converse、目标端保持 Chat Completions 后，两组模型组合的摘要场景共 6 个结果均有文本输出并正常结束（`end_turn`）。这验证了该迁移路径的摘要调用，不代表所有场景和工具参数均兼容。证据：`.deploy/converse-chat-regression.json`。
模型目录可见不代表该模型支持所有 API；此结果仅适用于这些模型在该端点的本次测试，不能推广到所有 Claude 模型或 Mantle。

界面现在对上述两个 Claude + Chat 组合显示已知失败提示，其他 HTTP API 组合显示需要实测的提示。保留运行入口，以支持负向兼容性演示。服务端遇到 `model_not_found` 时保留原始错误，并补充所选模型、端点及修正建议；不会自动切换 API 或将失败计为成功。

部署后在线复核已确认：Opus + Chat 返回原始 404 和新增 `errorHint`，其中包含实际模型 ID、Runtime URL 和切换建议；同一次请求的 Sol 直接替换及适配结果均正常结束。证据：`.deploy/chat-error-hint-regression.json`。本地 22 项单元测试及前端 JavaScript 语法检查通过。

此前 `API_MATRIX_VERIFICATION.md` 的 Chat/Responses 来源为 GPT，未覆盖本次 Claude + Chat 组合，其统计不包含本次复核。

复核命令：

```bash
python3 deploy/verify_scenarios.py --source-api chat --target-api chat --scenarios summary --output .deploy/chat-404-reproduction.json
python3 deploy/verify_scenarios.py --source-api converse --target-api chat --scenarios summary --output .deploy/converse-chat-regression.json
```
