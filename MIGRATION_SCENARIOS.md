# Bedrock Claude → GPT 迁移演示与验收矩阵

## 当前可运行：18 个场景

页面三列：源模型基线、目标模型直接替换、目标模型提示词及参数适配。迁移前后 API 可独立选择。第二列携带源模型 additionalModelRequestFields；第三列使用目标参数。API 报错也是兼容性实验结果，不能解释为模型质量低。

| 场景 | 演示内容 | 验证边界 |
|---|---|---|
| 客服摘要 | 意图与已执行动作的区分 | 非空检查；事实正确性人工评分 |
| JSON 抽取 | 类型、必填字段、多余字段、代码围栏 | 本地 JSON 校验，不是 API 原生结构化输出 |
| 固定资料 RAG | 引用与资料不足时拒绝猜测 | 引用格式检查；没有真实检索服务 |
| 订单工具 | toolUse / toolResult 往返 | 工具成功与 ID 对应 |
| 依赖式 Agent | 订单→地区政策→退款计算 | 调用跨轮、参数来源、执行顺序 |
| 多工具 Agent | A100、A200 独立查询 | 两订单覆盖；是否同轮调用作为观察项，宿主顺序执行本地工具 |
| 错误恢复 Agent | A404 不存在→A100 | error 状态回传与参数纠正 |
| Thinking | 分步优惠计算 | 源默认 enabled / budget_tokens=1024；答案应为 204 元，由人工检查 |
| Thinking + 工具 | 推理块与工具往返共存 | 原样保留消息、签名及 redactedContent；报告只导出块数量 |
| 多轮纠正 | A100→A200、未批准退款 | 消息历史隔离；最新事实人工检查 |
| 提示注入 | 检索文本试图篡改回答 | 标记泄露检查；不是完整安全评估 |
| 流式 API | ConverseStream / InvokeModelWithResponseStream / Responses SSE / Chat Completions SSE 文本事件 | 首文本耗时、事件计数、结束事件、流异常；UI 最终整组展示 |
| 截断 | maxTokens=32 | max_tokens 表示截断检测通过；允许无可见文本，回答仍不完整 |
| 字符与转义 | 中文、Unicode、emoji、引号和反斜杠 | 严格匹配文本往返 |
| 角色优先级 | system 与 user 指令冲突 | 检查 system 指定标记 |
| 历史消息顺序 | A100 被 A200 覆盖 | 检查最新值 |
| 工具错误状态 | 查询不存在的 A404 | 错误状态、调用参数与响应标记 |
| 停止序列 | stopSequences → stop_sequences / stop | 检查输出与结束原因；GPT stop 无法单独证明命中停止序列 |

默认每组最多 6 次模型请求、12 次工具调用。工具均为本地固定数据且没有付款、退款等写入动作。累计 token 是服务返回值；流中断且未收到 usage 时可能低估，不能当作账单。单次耗时包含网络、重试与工具往返，不是统计基准。

## API 与模型支持原则

当前支持 **Bedrock Runtime Converse / ConverseStream、InvokeModel / InvokeModelWithResponseStream、Responses、Chat Completions**，入口 us-east-1。InvokeModel 使用 Claude Messages 或 GPT Chat Completions 请求体；**未实现 Mantle 或提供商直连端点**。模型目录可见不代表具备调用权限或支持特定参数。美国 inference profile 可能跨美国区域路由，以页面目录为准。

Thinking 默认参数是兼容性探测，不保证每个 Claude 模型支持 enabled 模式。支持 adaptive 的模型应按该模型文档设置源参数。GPT 推理参数不得从 Claude budget_tokens 机械换算；目标参数输入框默认 {}，但 GPT 5.6 sol 的 InvokeModel / Chat Completions 工具场景在适配列未显式指定 reasoning_effort 时会补入 none，并展示适配说明。这不代表保留 Claude thinking 或双方推理预算相等。通过参数 JSON 显式指定目标模型支持的字段。签名只回传给产生它的同一模型会话，不将 Claude reasoning 历史迁给 GPT。

本次实测 Opus 4.8 拒绝 enabled，接受 `{"thinking":{"type":"adaptive"},"output_config":{"effort":"medium"}}` 并完成带签名 reasoning 的工具往返；页面提供快捷设置。该观察仅适用于本次所测模型，不能推广至所有 Claude。

参考：
- https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html

## 下一阶段：尚未实现的完整验收场景

| 领域 | 应增加的用例与验收条件 |
|---|---|
| Mantle | 独立适配器比较端点、认证、model ID、请求及响应字段；不要假定 Runtime model ID 可直接用于 Mantle |
| 参数支持矩阵 | 每个具体模型探测 temperature/topP、stop sequences、reasoning 模式、toolChoice、schema strict；记录支持、拒绝、未测，不能仅因 200 就断言参数生效 |
| 原生结构化输出 | 嵌套 schema、enum、nullable、additionalProperties、无效 schema、拒答及截断；区分 JSON 解析成功与语义正确 |
| 工具协议异常 | 重复/缺失 ID、未知工具、损坏参数、混合文本和工具、空响应、工具结果过大、部分失败、乱序返回、强制工具选择 |
| 有副作用的 Agent | 沙盒写入工具、幂等键、重复请求、超时后的未知状态、补偿与人工确认；禁止将自动重试当作业务幂等 |
| 复杂会话 | 10–50 轮、上下文压缩后事实保持、会话隔离、取消恢复、模型中途切换；签名历史不能跨提供商复用 |
| Thinking 变体 | enabled/adaptive/关闭、预算边界、与采样参数及工具组合、reasoning 流式块、签名缺失/篡改负例；不公开内部推理文本 |
| 多模态 | 图片/PDF/表格、格式及大小边界、OCR事实、引用来源、不同模型能力缺失提示 |
| 长上下文 | 输入接近限制与超限、资料头中尾事实、输入/输出 token 差异、工具结果膨胀 |
| 缓存 | 冷热请求、缓存写入/命中 token、TTL、内容变动失效；价格按真实型号和使用区域核实 |
| RAG 与安全 | 真实检索、召回一致性、冲突文档、缺失证据、工具输出注入、敏感数据、Guardrails 支持与拒答事件 |
| AWS 运行条件 | IAM/SCP、权限不足、模型访问资格、区域/跨区域路由、PrivateLink、凭证过期、配额、CloudTrail/日志脱敏 |
| 故障与流式 | 429/5xx、退避抖动、读超时、断流、客户端取消、重复提交、重试计费、限流和并发隔离 |
| 质量/成本/性能 | 固定版本数据集，多次运行；任务成功率、格式有效率、工具成功率、首文本/总延迟 P50/P95、每任务成本；评审盲测和人工复核 |
| 发布回滚 | 离线门槛、影子流量、灰度分流、模型版本固定、回退条件、会话黏性和回滚演练 |

完整验收应按“模型 × 端点/API × 场景 × 参数模式”记录结果，同时保存请求配置、服务版本/模型 ID、时间、轮次、usage、错误码和人工评分。不得用一次样例通过代替生产兼容性结论。

## 协议映射与复测

| 语义 | Converse | Claude InvokeModel | GPT InvokeModel |
|---|---|---|---|
| 输出上限 | maxTokens | max_tokens | max_completion_tokens |
| 系统指令 | system | system | messages 中 system |
| 工具请求 | toolUse | tool_use | tool_calls，arguments 为 JSON 字符串 |
| 工具返回 | toolResult | tool_result | role=tool，tool_call_id |
| 工具错误 | status=error | is_error=true | content JSON 中保留 status |
| 截断结束 | max_tokens | max_tokens | length（统一显示 max_tokens） |

协议转换在所有对比组中执行；“直接替换”保留源提示词和附加参数，并不表示把 Claude 请求体原样发给 GPT。流式适配目前仅覆盖文本，工具和 thinking 工具场景使用非流式调用。

```bash
python3 deploy/verify_scenarios.py --source-api converse --target-api invoke --adaptive --output .deploy/api-converse-invoke.json
python3 deploy/verify_scenarios.py --source-api invoke --target-api converse --adaptive --output .deploy/api-invoke-converse.json
```
