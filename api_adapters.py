"""Bedrock Runtime wire protocols; canonical messages stay local to each run."""
import base64
import json

APIS = {
    "responses": "Responses（HTTP / SSE）",
    "chat": "Chat Completions（HTTP / SSE）",
    "converse": "Converse（流式场景使用 ConverseStream）",
    "invoke": "InvokeModel（流式场景使用 InvokeModelWithResponseStream）",
}


def is_claude(model):
    return "anthropic." in model


def native_request(request):
    claude = is_claude(request["modelId"])
    config = request["inferenceConfig"]
    body = {"messages": []}
    system = "\n".join(x["text"] for x in request.get("system", []))
    if claude:
        body.update(anthropic_version="bedrock-2023-05-31", system=system,
                    max_tokens=config["maxTokens"])
    else:
        body["messages"].append({"role": "system", "content": system})
        body["max_completion_tokens"] = config["maxTokens"]
    for message in request["messages"]:
        if "_native" in message:
            body["messages"].append(message["_native"])
            continue
        if claude:
            blocks = []
            for block in message["content"]:
                if "text" in block:
                    blocks.append({"type": "text", "text": block["text"]})
                elif "toolUse" in block:
                    tool = block["toolUse"]
                    blocks.append({"type": "tool_use", "id": tool["toolUseId"],
                                   "name": tool["name"], "input": tool["input"]})
                elif "toolResult" in block:
                    tool = block["toolResult"]
                    blocks.append({"type": "tool_result", "tool_use_id": tool["toolUseId"],
                                   "is_error": tool.get("status") == "error",
                                   "content": "\n".join(x["text"] for x in tool["content"])})
                else:
                    raise ValueError("不支持转换此 Claude 消息内容块")
            body["messages"].append({"role": message["role"], "content": blocks})
        else:
            texts, calls = [], []
            for block in message["content"]:
                if "text" in block:
                    texts.append(block["text"])
                elif "toolUse" in block:
                    tool = block["toolUse"]
                    calls.append({"id": tool["toolUseId"], "type": "function",
                                  "function": {"name": tool["name"],
                                               "arguments": json.dumps(tool["input"], ensure_ascii=False)}})
                elif "toolResult" in block:
                    tool = block["toolResult"]
                    # Chat Completions has no tool-result status field. Preserve it in content.
                    body["messages"].append({"role": "tool", "tool_call_id": tool["toolUseId"],
                        "content": json.dumps({"status": tool.get("status", "success"),
                            "content": tool["content"]}, ensure_ascii=False)})
                else:
                    raise ValueError("不支持转换此 GPT 消息内容块")
            if texts or calls:
                item = {"role": message["role"], "content": "\n".join(texts) or None}
                if calls:
                    item["tool_calls"] = calls
                body["messages"].append(item)
    for key, value in config.items():
        mapping = {"temperature": "temperature", "topP": "top_p",
                   "stopSequences": "stop_sequences" if claude else "stop"}
        if key in mapping:
            body[mapping[key]] = value
    tools = request.get("toolConfig", {}).get("tools", [])
    if tools:
        if claude:
            body["tools"] = [{"name": x["toolSpec"]["name"],
                "description": x["toolSpec"]["description"],
                "input_schema": x["toolSpec"]["inputSchema"]["json"]} for x in tools]
        else:
            body["tools"] = [{"type": "function", "function": {
                "name": x["toolSpec"]["name"], "description": x["toolSpec"]["description"],
                "parameters": x["toolSpec"]["inputSchema"]["json"]}} for x in tools]
    fields = request.get("additionalModelRequestFields", {})
    reserved = {"messages", "system", "tools", "model", "stream", "anthropic_version",
                "max_tokens", "max_completion_tokens"}
    if reserved.intersection(fields):
        raise ValueError("附加参数不能覆盖消息、工具、模型、流模式或 token 上限")
    body.update(fields)
    return body


def stop_reason(reason):
    return {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use",
            "function_call": "tool_use"}.get(reason, reason)


def native_response(data, claude):
    content = []
    if claude:
        native = {"role": "assistant", "content": data.get("content", [])}
        for block in native["content"]:
            kind = block["type"]
            if kind == "text":
                content.append({"text": block["text"]})
            elif kind == "tool_use":
                content.append({"toolUse": {"toolUseId": block["id"], "name": block["name"], "input": block["input"]}})
            elif kind == "thinking":
                content.append({"reasoningContent": {"reasoningText": {
                    "text": block["thinking"], "signature": block.get("signature", "")}}})
            elif kind == "redacted_thinking":
                content.append({"reasoningContent": {"redactedContent": base64.b64decode(block["data"])}})
        raw_stop = data.get("stop_reason")
        stats = data.get("usage", {})
        usage = {"inputTokens": stats.get("input_tokens", 0), "outputTokens": stats.get("output_tokens", 0)}
    else:
        choice = data["choices"][0]
        native = choice["message"]
        if native.get("content"):
            if not isinstance(native["content"], str):
                raise ValueError("GPT 返回非文本 content，当前适配器不支持")
            content.append({"text": native["content"]})
        for tool in native.get("tool_calls", []):
            content.append({"toolUse": {"toolUseId": tool["id"], "name": tool["function"]["name"],
                                       "input": json.loads(tool["function"]["arguments"])}})
        raw_stop = choice.get("finish_reason")
        stats = data.get("usage", {})
        usage = {"inputTokens": stats.get("prompt_tokens", 0), "outputTokens": stats.get("completion_tokens", 0)}
    return {"output": {"message": {"role": "assistant", "content": content, "_native": native}},
            "stopReason": stop_reason(raw_stop), "nativeStopReason": raw_stop, "usage": usage}


class NativeStream:
    """Expose text-only native events in the same shape as ConverseStream."""
    def __init__(self, stream, claude):
        self.stream, self.claude = stream, claude

    def close(self):
        self.stream.close()

    def __iter__(self):
        for event in self.stream:
            if "chunk" not in event:
                yield event
                continue
            data = json.loads(event["chunk"]["bytes"])
            if self.claude:
                kind = data.get("type")
                if kind == "error":
                    raise RuntimeError(json.dumps(data, ensure_ascii=False))
                if kind == "content_block_start" and data.get("content_block", {}).get("type") == "tool_use":
                    raise ValueError("文本流场景不接受工具请求")
                if kind == "content_block_delta" and data.get("delta", {}).get("type") == "text_delta":
                    yield {"contentBlockDelta": {"delta": {"text": data["delta"]["text"]}}}
                if kind == "message_start":
                    stats = data["message"].get("usage", {})
                    yield {"metadata": {"usage": {"inputTokens": stats.get("input_tokens", 0)}}}
                if kind == "message_delta":
                    reason = data.get("delta", {}).get("stop_reason")
                    if reason:
                        yield {"messageStop": {"stopReason": stop_reason(reason)}}
                    if "usage" in data:
                        yield {"metadata": {"usage": {"outputTokens": data["usage"].get("output_tokens", 0)}}}
            else:
                if data.get("error"):
                    raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta.get("tool_calls"):
                        raise ValueError("文本流场景不接受工具请求")
                    if delta.get("content"):
                        yield {"contentBlockDelta": {"delta": {"text": delta["content"]}}}
                    if choice.get("finish_reason"):
                        yield {"messageStop": {"stopReason": stop_reason(choice["finish_reason"])}}
                if data.get("usage"):
                    stats = data["usage"]
                    yield {"metadata": {"usage": {"inputTokens": stats.get("prompt_tokens", 0),
                                                   "outputTokens": stats.get("completion_tokens", 0)}}}


def invoke(runtime, request, stream=False):
    body = native_request(request)
    kwargs = {"modelId": request["modelId"], "contentType": "application/json",
              "accept": "application/json", "body": json.dumps(body, ensure_ascii=False).encode()}
    if stream:
        response = runtime.invoke_model_with_response_stream(**kwargs)
        return {"stream": NativeStream(response["body"], is_claude(request["modelId"])),
                "ResponseMetadata": response.get("ResponseMetadata", {})}
    response = runtime.invoke_model(**kwargs)
    try:
        data = json.loads(response["body"].read())
    finally:
        response["body"].close()
    return {**native_response(data, is_claude(request["modelId"])),
            "ResponseMetadata": response.get("ResponseMetadata", {})}
