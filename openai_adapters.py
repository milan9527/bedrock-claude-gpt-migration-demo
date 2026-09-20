"""Actual Bedrock Runtime OpenAI HTTP APIs, authenticated with the ECS role."""
import json
import urllib.request
import urllib.error
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from api_adapters import native_request, native_response

PATHS = {'chat': '/openai/v1/chat/completions', 'responses': '/openai/v1/responses'}


def request_body(request, api):
    fields = request.get('additionalModelRequestFields', {})
    if set(fields) & {'input', 'instructions', 'max_output_tokens', 'store', 'previous_response_id', 'conversation'}:
        raise ValueError('附加参数不能覆盖消息、会话或 token 上限')
    # Use the Chat wire schema regardless of the selected provider; let Bedrock
    # report unsupported model/API combinations without silently changing APIs.
    chat = native_request({**request, 'modelId': 'openai.wire-format', 'messages': request['messages'] if api == 'chat' else []})
    chat['model'] = request['modelId']
    if api == 'chat':
        return chat
    body = {'model': request['modelId'], 'instructions': '\n'.join(x['text'] for x in request.get('system', [])),
            'input': [], 'max_output_tokens': request['inferenceConfig']['maxTokens'], 'store': False}
    for message in request['messages']:
        if '_responses' in message:
            body['input'].extend(message['_responses'])
            continue
        for block in message['content']:
            if 'text' in block:
                body['input'].append({'role': message['role'], 'content': block['text']})
            elif 'toolUse' in block:
                tool = block['toolUse']
                body['input'].append({'type': 'function_call', 'call_id': tool['toolUseId'],
                    'name': tool['name'], 'arguments': json.dumps(tool['input'], ensure_ascii=False)})
            elif 'toolResult' in block:
                tool = block['toolResult']
                body['input'].append({'type': 'function_call_output', 'call_id': tool['toolUseId'],
                    'output': json.dumps({'status': tool.get('status', 'success'), 'content': tool['content']}, ensure_ascii=False)})
    if chat.get('tools'):
        body['tools'] = [{'type': 'function', **x['function']} for x in chat['tools']]
    for key in ('temperature', 'top_p', 'stop'):
        if key in chat:
            body[key] = chat[key]
    body.update(fields)
    return body


def response_body(data):
    if data.get('error') or data.get('status') not in ('completed', 'incomplete'):
        raise RuntimeError(json.dumps(data.get('error') or {'status': data.get('status')}, ensure_ascii=False))
    content = []
    for item in data.get('output', []):
        if item['type'] == 'message':
            for block in item.get('content', []):
                if block['type'] == 'output_text':
                    content.append({'text': block['text']})
                elif block['type'] == 'refusal':
                    content.append({'text': block['refusal']})
        elif item['type'] == 'function_call':
            content.append({'toolUse': {'toolUseId': item['call_id'], 'name': item['name'], 'input': json.loads(item['arguments'])}})
        elif item['type'] == 'reasoning':
            content.append({'reasoningContent': {}})
    reason = data.get('incomplete_details', {}).get('reason') if data.get('incomplete_details') else None
    stop = ('max_tokens' if reason == 'max_output_tokens' else reason or 'incomplete') if data['status'] == 'incomplete' else ('tool_use' if any('toolUse' in x for x in content) else 'end_turn')
    stats = data.get('usage') or {}
    return {'output': {'message': {'role': 'assistant', 'content': content, '_responses': data.get('output', [])}},
            'stopReason': stop, 'nativeStopReason': reason or data['status'],
            'usage': {'inputTokens': stats.get('input_tokens', 0), 'outputTokens': stats.get('output_tokens', 0)}}


class SSEStream:
    def __init__(self, response, api):
        self.response, self.api = response, api

    def close(self):
        self.response.close()

    def __iter__(self):
        lines = []
        for line in self.response:
            line = line.decode('utf-8').rstrip('\r\n')
            if line:
                if line.startswith('data:'):
                    lines.append(line[5:].lstrip())
                continue
            if not lines:
                continue
            raw, lines = '\n'.join(lines), []
            if raw == '[DONE]':
                continue
            data = json.loads(raw)
            if data.get('error') or data.get('type') in ('error', 'response.failed'):
                raise RuntimeError(json.dumps(data, ensure_ascii=False))
            if self.api == 'responses':
                kind = data.get('type')
                if kind == 'response.output_text.delta':
                    yield {'contentBlockDelta': {'delta': {'text': data['delta']}}}
                elif kind == 'response.output_item.added' and data.get('item', {}).get('type') == 'function_call':
                    raise ValueError('文本流场景不接受工具请求')
                elif kind in ('response.completed', 'response.incomplete'):
                    normalized = response_body(data['response'])
                    yield {'messageStop': {'stopReason': normalized['stopReason']}}
                    yield {'metadata': {'usage': normalized['usage']}}
            else:
                for choice in data.get('choices', []):
                    delta = choice.get('delta', {})
                    if delta.get('tool_calls'):
                        raise ValueError('文本流场景不接受工具请求')
                    if delta.get('content'):
                        yield {'contentBlockDelta': {'delta': {'text': delta['content']}}}
                    if choice.get('finish_reason'):
                        from api_adapters import stop_reason
                        yield {'messageStop': {'stopReason': stop_reason(choice['finish_reason'])}}
                if data.get('usage'):
                    stats = data['usage']
                    yield {'metadata': {'usage': {'inputTokens': stats.get('prompt_tokens', 0), 'outputTokens': stats.get('completion_tokens', 0)}}}


class OpenAIHTTP:
    def __init__(self, session, region):
        self.session, self.region = session, region
        self.endpoint = f'https://bedrock-runtime.{region}.amazonaws.com'

    def invoke(self, request, api, stream=False):
        body = request_body(request, api)
        body['stream'] = stream
        if stream and api == 'chat':
            body['stream_options'] = {'include_usage': True}
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
        url = self.endpoint + PATHS[api]
        signed = AWSRequest(method='POST', url=url, data=payload, headers={'Content-Type': 'application/json'})
        SigV4Auth(self.session.get_credentials().get_frozen_credentials(), 'bedrock', self.region).add_auth(signed)
        try:
            response = urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=dict(signed.headers)), timeout=120)
        except urllib.error.HTTPError as exc:
            with exc:
                detail = exc.read(16384).decode('utf-8', errors='replace')
            raise RuntimeError(f'Bedrock {api} HTTP {exc.code}: {detail}') from None
        metadata = {'HTTPStatusCode': response.status, 'RequestId': response.headers.get('x-amzn-requestid', '')}
        if stream:
            return {'stream': SSEStream(response, api), 'ResponseMetadata': metadata}
        with response:
            data = json.load(response)
        normalized = response_body(data) if api == 'responses' else native_response(data, False)
        return {**normalized, 'ResponseMetadata': metadata}
