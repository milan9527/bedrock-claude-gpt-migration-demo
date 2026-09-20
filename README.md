# Bedrock 模型迁移演示

前后端分离部署到 AWS，Bedrock 客户端区域默认为 `us-east-1`。通过账户实时模型目录选择 Claude → GPT，预设：

- Claude Opus 4.8 → GPT-5.6 Sol
- Claude Fable 5.1 → GPT-6 Astra

## AWS 部署（不用 CloudFormation）

```text
浏览器 HTTPS → CloudFront
                ├─ / → 私有 S3（OAC 签名）
                └─ /api/* → VPC origin → 内部 ALB → ECS Fargate → Bedrock Runtime
```

`deploy/deploy.py` 使用 boto3 直接创建 VPC、IAM、ECR、ECS、ALB、S3、OAC 和 CloudFront；不使用 CDK 或 CloudFormation。
需要 Python、Docker、AWS 部署权限和对应模型访问权限：

```bash
python3 -m pip install -r requirements.txt
python3 deploy/deploy.py
```

部署完成输出 HTTPS 地址，使用用户名 `admin` 和 `.deploy/login-password.txt` 中的密码登录。
密码作为 SSM SecureString 存储，由 ECS 注入容器；不使用 Cognito。登录后使用 Secure / HttpOnly / SameSite=Strict Cookie，会话有效期八小时；退出立即失效，ECS 重启需重新登录。前端不保存密码或 AWS 密钥。
`.deploy/state.json` 保存资源标识以便重跑，必须保留，不要提交 `.deploy/`。
重跑会构建新镜像并更新 ECS，上传前端并清理 CloudFront 缓存。
脚本用于此演示的创建及应用更新，不是通用基础设施差异管理工具。

API 请求提交后台任务并轮询结果，避免多轮推理超过 CloudFront 单次请求等待时间。
演示采用单个 Fargate task，每次只接受一个三组对比任务；任务保存在内存，重启会丢失，不能直接扩容为多个 task。
前端静态文件独立位于 `frontend/`。本地 `python3 app.py` 仅启动 API（127.0.0.1:8090）；可用 curl 测试 `/api/health`、`/api/catalog`。
本地通过 `DEMO_USERNAME`（默认 admin）与 `DEMO_PASSWORD` 配置账户；未配置密码时禁止登录。登录 Cookie 要求 HTTPS，本地 HTTP 测试需手动传 Cookie。

ALB 位于私有子网，只允许 CloudFront VPC origin 安全组访问。
ECS 位于有公网出口的子网以拉取镜像及调用 Bedrock，入站只允许 ALB，不创建 NAT Gateway。
静态桶禁止公开访问，桶策略仅授权本分配的 OAC 请求。
ECS、ALB、公网 IPv4、CloudFront、日志和模型调用会产生费用；停止演示后需要删除资源。

## 演示流程

1. 选择迁移组合，或分别选择源模型、目标模型。
2. 分别选择源 API 和目标 API（Converse、InvokeModel、Responses 或 Chat Completions），从 18 个场景选择摘要、JSON、RAG、Agent 多轮工具、thinking、对话纠正、提示注入、流式响应或输出截断。
3. 运行三列对比：源模型基线、目标模型直接替换、目标模型提示词及参数适配。可展开修改两侧的模型附加参数 JSON。
4. 查看文本、总延迟、输入/输出 token、格式检查、实际系统提示词及工具轨迹。
5. 导出 JSON，记录结果与模型 ID；适配提示词只是候选方案，不预设一定优于基线。

## 范围和限制

- 默认自定义选择；目录动态展示 ACTIVE 的美国系统推理配置和区域内 ACTIVE 的按需 Claude/GPT 模型，排除专用 safeguard 模型。两组预设仅为快捷入口。
- 使用 Bedrock Runtime Converse / ConverseStream、InvokeModel / InvokeModelWithResponseStream，以及独立的 Responses / Chat Completions HTTP API，默认端点 `https://bedrock-runtime.us-east-1.amazonaws.com`，未使用 Mantle；页面显示实际 API 和端点路径。
- 目录可见不保证可调用或支持每种功能，单组调用错误在页面显示。
- `us-east-1` 是 API 入口。`us.` 配置可跨美国区域推理；页面显示配置包含的区域，并非本次调用的实际执行位置。
- RAG 场景使用固定资料，便于控制变量；未部署 Knowledge Bases 或向量数据库。
- 工具查询本地 A100/A200 样例订单和政策，计算退款资格，支持错误恢复和依赖式调用；不执行真实退款。每组最多六轮模型调用、十二次工具执行。
- JSON 使用提示词约束和本地字段校验，不依赖原生 structured outputs。
- 自动检查不代表语义正确率。修改输入后，需要人工核对事实；报告保留原输入和资料。
- 流式场景消费所选 API 的文本事件并记录首文本延迟；页面在三组完成后展示。多轮对话使用固定历史，尚未提供交互式聊天。
- Thinking 场景默认给 Claude 传 enabled/budget_tokens=1024，是否接受取决于模型；GPT 适配默认不带此参数，不代表等价推理配置。工具往返保留原始签名消息，报告不导出推理正文。
- 单次运行并行执行三组推理，每组最多六次模型调用；普通场景输出上限 1024 token，thinking 场景 4096，截断场景 32；真实调用计费。
- [完整场景与待验证矩阵](MIGRATION_SCENARIOS.md) 列明已实现范围，以及 Mantle、多模态、长上下文、权限、限流、缓存、批量质量评测等后续验证项目。
- 云端使用一个演示账户；登录限制为全站每分钟 20 次，最多保留 100 个会话。尚未实现账户注册、密码找回、权限分级或按用户配额。

## 验证

已部署演示入口：https://d15ilm7z7pa2xp.cloudfront.net 。用户名 `admin`，密码见本地 `.deploy/login-password.txt`。
本次验证覆盖两个模型组合、18 个场景，以及 Converse → InvokeModel 和 InvokeModel → Converse 两个方向；每个用例比较源模型、直接迁移和适配后三列。具体结果、失败原因和原始证据见 [场景验证报告](SCENARIO_VERIFICATION.md)。通过表示当前自动检查通过，不代表所有模型、API 或语义质量均已验证。

复测命令（产生真实模型调用费用）：

```bash
python3 deploy/verify_scenarios.py --source-api converse --target-api invoke --adaptive --output .deploy/api-converse-invoke.json
python3 deploy/verify_scenarios.py --source-api invoke --target-api converse --adaptive --output .deploy/api-invoke-converse.json
```

`--adaptive` 为 thinking 场景设置 Claude adaptive + medium effort；不带此参数时探测旧式 enabled。直接迁移保留源附加参数，因此 GPT 拒绝 Claude 专有字段时会显示真实错误。适配后移除这些字段，不代表启用了等价的 GPT reasoning 模式。

截断场景故意将输出预算设为 32 tokens，以 `stopReason=max_tokens` 作为检测通过条件；输出可以为空，不能据此认为回答完整。普通场景仍要求 `end_turn`。

本地 21 项回归测试通过；前端 JavaScript 语法检查在此前部署时通过：

```bash
python3 -m unittest discover -s tests -v
```

GPT 5.6 sol 原生 Chat Completions 的工具场景：适配后列在未指定 reasoning_effort 时补入 `none`，以满足实测服务约束；直接替换列保留原始配置。界面显示该适配，明确它不等于保留 Claude thinking 能力，用户显式提供的推理参数不会被覆盖。

实测 GPT 6 Astra 原生 Chat Completions 不支持当前工具与推理组合，也不接受 `reasoning_effort=none`，因此不套用 GPT 5.6 的补丁，保留服务错误。两种 GPT 的原生接口均拒绝 `stop` 参数。切换目标 API 后需重新验证，不将删参视作语义等价迁移。

## Responses 和 Chat Completions

两侧 API 选择器均提供四种 API。新增接口使用 ECS 任务角色进行 SigV4 签名（service `bedrock`），不需要 OpenAI API key：

| API | Bedrock Runtime HTTP 路径 |
| --- | --- |
| Responses | `/openai/v1/responses` |
| Chat Completions | `/openai/v1/chat/completions` |

这是对独立 HTTP 接口的实际调用。Responses 使用 `input`、`max_output_tokens`、扁平 function 工具和 `function_call_output`；Chat Completions 使用 `messages`、`max_completion_tokens`、`tool_calls` 和 tool 消息。Responses 每轮回传原始 output items（含 reasoning 和 function call），设置 `store=false`；未实现服务端 conversation / previous_response_id 会话管理。

ECS task role 使用 SigV4 认证。部署脚本除模型与 inference profile 权限外，还授予当前账户、当前区域 `project/default` 的调用权限，满足新增 HTTP API 的权限检查。

18 个既有场景均可选择新 API。文本流消费 SSE；工具场景使用非流式多轮调用。暂未实现流式工具参数拼接。模型不支持某 API、参数或工具组合时展示真实错误，不自动切换 API。JSON 抽取场景仍是文本 JSON 校验，不等同于原生 Structured Outputs。

新增测试验证请求格式、工具 call ID 与 reasoning 回传、SSE 截断结束和错误事件。实测证据及限制见 [HTTP API 验证报告](HTTP_API_VERIFICATION.md)。

新增跨 API 实测覆盖四种 API 的 16 种前后组合，并补测两组 Claude → GPT 的扩展场景。分组结果、实际模型、失败原因及覆盖边界见 [多场景、多 API 验证报告](API_MATRIX_VERIFICATION.md)。

Claude Converse → GPT Chat Completions / Responses 的九场景专项复测见
[Claude → GPT 扩展验证报告](CLAUDE_GPT_EXTENDED_VERIFICATION.md)，包含工具推理限制、thinking 参数和停止序列的实际失败结果。

既有 API 矩阵的复测和汇总命令：

```bash
python3 deploy/verify_api_matrix.py
python3 deploy/summarize_api_matrix.py
```
