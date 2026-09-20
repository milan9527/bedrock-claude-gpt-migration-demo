import io
import json
import unittest
from openai_adapters import request_body, response_body, SSEStream


class OpenAIHTTPTests(unittest.TestCase):
    def request(self):
        return dict(modelId='us.openai.test', system=[{'text': '规则'}],
                    messages=[{'role': 'user', 'content': [{'text': '订单🚚'}]}],
                    inferenceConfig={'maxTokens': 100})

    def test_distinct_wire_schemas(self):
        chat = request_body(self.request(), 'chat')
        responses = request_body(self.request(), 'responses')
        self.assertEqual(chat['messages'][1]['content'], '订单🚚')
        self.assertEqual(chat['max_completion_tokens'], 100)
        self.assertEqual(responses['input'][0]['content'], '订单🚚')
        self.assertEqual(responses['max_output_tokens'], 100)
        self.assertFalse(responses['store'])
        self.assertNotIn('messages', responses)

    def test_responses_reasoning_and_tool_replay(self):
        output = [{'type': 'reasoning', 'id': 'r1', 'encrypted_content': 'opaque', 'summary': []},
                  {'type': 'function_call', 'id': 'f1', 'call_id': 'c1', 'name': 'lookup', 'arguments': '{"id":1}'}]
        normalized = response_body({'status': 'completed', 'output': output})
        req = self.request()
        req['messages'].append(normalized['output']['message'])
        req['messages'].append({'role': 'user', 'content': [{'toolResult': {
            'toolUseId': 'c1', 'status': 'error', 'content': [{'text': 'missing'}]}}]})
        wire = request_body(req, 'responses')
        self.assertEqual(wire['input'][1:3], output)
        self.assertEqual(wire['input'][3]['call_id'], 'c1')
        self.assertEqual(json.loads(wire['input'][3]['output'])['status'], 'error')

    def test_sse_incomplete_and_usage(self):
        events = [{'type': 'response.output_text.delta', 'delta': '你好'},
                  {'type': 'response.incomplete', 'response': {'status': 'incomplete',
                   'incomplete_details': {'reason': 'max_output_tokens'}, 'output': [],
                   'usage': {'input_tokens': 3, 'output_tokens': 5}}}]
        raw = ''.join('data: ' + json.dumps(e) + '\r\n\r\n' for e in events).encode()
        stream = SSEStream(io.BytesIO(raw), 'responses')
        result = list(stream)
        self.assertEqual(result[0]['contentBlockDelta']['delta']['text'], '你好')
        self.assertEqual(result[1]['messageStop']['stopReason'], 'max_tokens')
        self.assertEqual(result[2]['metadata']['usage']['outputTokens'], 5)
        stream.close()
        self.assertTrue(stream.response.closed)

    def test_errors_not_success(self):
        with self.assertRaises(RuntimeError):
            response_body({'status': 'failed', 'error': {'message': 'failure'}})
        with self.assertRaises(RuntimeError):
            list(SSEStream(io.BytesIO(b'data: {"type":"error","message":"failure"}\n\n'), 'chat'))

    def test_cannot_override_session(self):
        req = self.request()
        req['additionalModelRequestFields'] = {'previous_response_id': 'hidden'}
        with self.assertRaises(ValueError):
            request_body(req, 'responses')
