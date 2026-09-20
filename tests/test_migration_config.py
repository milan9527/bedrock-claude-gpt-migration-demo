import unittest
from unittest.mock import Mock
from app import Workbench
from migration_config import validate_config, output_checks, suggestions
from api_adapters import native_request
from openai_adapters import request_body


class ConfigTests(unittest.TestCase):
    def test_validation_rejects_invalid_values(self):
        for config in [[], {'maxTokens': True}, {'maxTokens': 1.5},
                       {'temperature': float('nan')}, {'topP': 2},
                       {'stream': 'true'}, {'stopSequences': ['']},
                       {'outputCheck': 'xml'}, {'unknown': 1}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_config(config)

    def test_api_parameter_mapping(self):
        config = validate_config({'maxTokens': 128, 'temperature': .5, 'topP': .9,
                                  'stopSequences': ['END']})
        request = {'modelId': 'us.openai.test', 'messages': [
            {'role': 'user', 'content': [{'text': 'test'}]}], 'inferenceConfig': config}
        for api, token_key in [('chat', 'max_completion_tokens'), ('responses', 'max_output_tokens')]:
            body = request_body(request, api)
            self.assertEqual(body[token_key], 128)
            self.assertEqual(body['temperature'], .5)
            self.assertEqual(body['top_p'], .9)
        request['modelId'] = 'us.anthropic.test'
        body = native_request(request)
        self.assertEqual(body['max_tokens'], 128)
        self.assertEqual(body['stop_sequences'], ['END'])

    def test_output_check_and_advice(self):
        for text in ('not JSON', '{"x":NaN}', '{"partial":'):
            checks = output_checks(text, 'json')
            self.assertFalse(all(checks.values()))
            self.assertTrue(suggestions({'checks': checks}))
        self.assertTrue(all(output_checks('{"ok":true}', 'json').values()))
        self.assertTrue(suggestions({'error': 'HTTP 404 model_not_found'}))
        self.assertTrue(suggestions({'error': 'unsupported thinking'}))

    def test_converse_override_and_stream_tool_guard(self):
        bench = Workbench.__new__(Workbench)
        bench.runtime = Mock()
        bench.runtime.converse.return_value = {'output': {'message': {
            'role': 'assistant', 'content': [{'text': '{"ok":true}'}]}}, 'stopReason': 'end_turn'}
        result = bench.run('m', 'summary', '摘要', False,
                           config={'maxTokens': 123, 'outputCheck': 'json'})
        self.assertNotIn('error', result)
        self.assertEqual(bench.runtime.converse.call_args.kwargs['inferenceConfig']['maxTokens'], 123)
        self.assertTrue(result['checks']['输出校验：合法 JSON'])
        bench.runtime.reset_mock()
        guarded = bench.run('m', 'tools', '查询', False, config={'stream': True})
        self.assertIn('error', guarded)
        self.assertTrue(guarded['suggestions'])
        bench.runtime.converse.assert_not_called()
        bench.runtime.converse_stream.assert_not_called()

    def test_compare_preserves_distinct_configs(self):
        bench = Workbench.__new__(Workbench)
        bench.models = {'source': {}, 'target': {}}
        bench.run = Mock(return_value={})
        bench.compare({'source': 'source', 'target': 'target', 'scenario': 'summary',
                       'input': '摘要', 'sourceConfig': {'maxTokens': 100},
                       'targetConfig': {'maxTokens': 200}})
        configs = { (c.args[0], c.args[3]): c.args[6] for c in bench.run.call_args_list }
        self.assertEqual(configs[('source', False)], {'maxTokens': 100})
        self.assertEqual(configs[('target', False)], {'maxTokens': 100})
        self.assertEqual(configs[('target', True)], {'maxTokens': 200})
