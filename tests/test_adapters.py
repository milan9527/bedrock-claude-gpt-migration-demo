import io
import json
import unittest
from unittest.mock import Mock
from api_adapters import native_request, native_response, invoke, NativeStream


class AdapterTests(unittest.TestCase):
    def request(self, model='us.openai.test'):
        return dict(modelId=model, system=[{'text': '规则'}],
                    messages=[{'role': 'user', 'content': [{'text': '订单🚚'}]}],
                    inferenceConfig={'maxTokens': 100, 'stopSequences': ['END']})

    def test_native_parameters_and_tool_error(self):
        req = self.request()
        req['messages'].append({'role': 'user', 'content': [{'toolResult': {
            'toolUseId': 'call-1', 'status': 'error', 'content': [{'text': 'missing'}]}}]})
        gpt = native_request(req)
        self.assertEqual(gpt['max_completion_tokens'], 100)
        self.assertEqual(gpt['stop'], ['END'])
        self.assertEqual(gpt['messages'][-1]['tool_call_id'], 'call-1')
        self.assertEqual(json.loads(gpt['messages'][-1]['content'])['status'], 'error')
        req['modelId'] = 'us.anthropic.test'
        claude = native_request(req)
        self.assertEqual(claude['stop_sequences'], ['END'])
        self.assertTrue(claude['messages'][-1]['content'][0]['is_error'])

    def test_reasoning_and_tool_ids_survive_round_trip(self):
        blocks = [{'type': 'thinking', 'thinking': 'private', 'signature': 'opaque'},
                  {'type': 'tool_use', 'id': 'call-7', 'name': 'lookup', 'input': {'id': 7}}]
        response = native_response({'content': blocks, 'stop_reason': 'tool_use'}, True)
        req = self.request('us.anthropic.test')
        req['messages'].append(response['output']['message'])
        self.assertEqual(native_request(req)['messages'][-1]['content'], blocks)
        self.assertEqual(response['output']['message']['content'][1]['toolUse']['toolUseId'], 'call-7')

    def test_invalid_json_closes_body(self):
        body = io.BytesIO(b'invalid')
        runtime = Mock()
        runtime.invoke_model.return_value = {'body': body}
        with self.assertRaises(ValueError):
            invoke(runtime, self.request())
        self.assertTrue(body.closed)

    def test_gpt_stream_stop_and_usage(self):
        events = [{'choices': [{'delta': {'content': 'hello'}}]},
                  {'choices': [{'delta': {}, 'finish_reason': 'length'}]},
                  {'usage': {'prompt_tokens': 4, 'completion_tokens': 8}}]
        stream = NativeStream([{'chunk': {'bytes': json.dumps(e).encode()}} for e in events], False)
        out = list(stream)
        self.assertEqual(out[1]['messageStop']['stopReason'], 'max_tokens')
        self.assertEqual(out[2]['metadata']['usage']['outputTokens'], 8)

    def test_reserved_fields_rejected(self):
        req = self.request()
        req['additionalModelRequestFields'] = {'messages': []}
        with self.assertRaises(ValueError):
            native_request(req)
