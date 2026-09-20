"""User-controlled inference settings and actionable compatibility diagnostics."""
import json
import math


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('API 配置必须是 JSON 对象')
    allowed = {'maxTokens', 'temperature', 'topP', 'stopSequences', 'stream', 'outputCheck'}
    if set(config) - allowed:
        raise ValueError('未知 API 配置字段：' + ', '.join(sorted(set(config) - allowed)))
    for key, low, high in [('maxTokens', 1, 32768), ('temperature', 0, 2), ('topP', 0, 1)]:
        if key in config:
            value = config[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or (key == 'maxTokens' and not isinstance(value, int)):
                raise ValueError(f'{key} 必须在 {low}–{high} 范围内' + ('且为整数' if key == 'maxTokens' else ''))
    if 'stream' in config and not isinstance(config['stream'], bool):
        raise ValueError('stream 必须为 true 或 false')
    if config.get('outputCheck', 'default') not in ('default', 'text', 'json'):
        raise ValueError('outputCheck 请选择 default / text / json')
    stops = config.get('stopSequences', [])
    if not isinstance(stops, list) or len(stops) > 4 or any(not isinstance(s, str) or not 1 <= len(s) <= 256 for s in stops):
        raise ValueError('停止序列最多 4 个，每个为 1–256 字符的字符串')
    return config


def output_checks(text, mode):
    if mode == 'text':
        return {'输出校验：非空文本': bool(text.strip())}
    if mode == 'json':
        try:
            json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            valid = True
        except (ValueError, TypeError):
            valid = False
        return {'输出校验：合法 JSON': valid}
    return {}


def suggestions(result):
    error = result.get('error', '').lower()
    tips = []
    if 'model_not_found' in error or '404' in error:
        tips.append('核对当前区域、模型 ID 和 API 支持范围；Claude 可尝试 Converse / InvokeModel，GPT 可分别探测 Responses 与 Chat Completions。目录可见不保证 API 支持。')
    if 'thinking' in error or 'reasoning' in error:
        tips.append('不要将 Claude thinking 原样传给 GPT。Claude 可探测 adaptive；GPT Chat 使用 reasoning_effort，Responses 使用 reasoning.effort。支持的取值取决于模型；清空参数后逐项验证。')
    if 'stop' in error:
        tips.append('移除停止序列再重试；部分 GPT API 不支持 stop。应用端停止需单独实现，不能当作服务端停止序列已支持。')
    if any(word in error for word in ('format', 'schema', 'output_config', 'response_format')):
        tips.append('检查输出格式字段：Chat 使用 response_format，Responses 使用 text.format；Converse 的附加字段依模型而定。先清空格式约束再验证模型的结构化输出支持。')
    if any(word in error for word in ('temperature', 'top_p', 'topp', 'token', 'parameter', '参数')):
        tips.append('恢复场景默认参数后逐项添加；temperature / top_p、token 上限及推理预算的允许范围依模型而异，部分模型不能同时指定两种采样参数。')
    if '工具' in error or 'tool' in error:
        tips.append('工具场景请选择非流式；检查工具参数和结果回传。GPT Chat 工具调用不兼容时可显式改选 Responses；本应用不会自动切换 API。')
    if any(word in error for word in ('accessdenied', '403', 'unauthorized')):
        tips.append('由管理员核对 ECS 任务角色的 Bedrock 调用权限、模型访问和跨区域推理权限。')
    if any(word in error for word in ('throttl', '429', 'timeout')):
        tips.append('降低请求频率或输出 token 数，检查对应模型配额后重试。')
    if error and not tips:
        tips.append('保留原始错误并查看请求详情；清空附加参数、恢复默认配置后重试，逐项确认当前模型与 API 支持的字段。')
    if result.get('stopReason') == 'max_tokens':
        tips.append('输出达到 token 上限；如需完整回答请提高上限并考虑推理 token 开销。截断测试中触发此状态是预期行为。')
    if result.get('checks', {}).get('输出校验：合法 JSON') is False:
        tips.append('输出不是合法 JSON。请明确提示仅输出 JSON，或为支持的模型配置原生 JSON 输出格式；检查是否因 token 上限导致截断。输出校验本身不会强制模型生成 JSON。')
    return tips
