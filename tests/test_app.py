import unittest
from unittest.mock import patch
from app import Workbench, execute_tool, evaluate


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            content = [{"toolUse": {"name": "get_order", "toolUseId": "t1",
                                   "input": {"order_id": "A100"}}}]
            stop = "tool_use"
        else:
            content = [{"text": "订单配送延迟，退款尚未批准。"}]
            stop = "end_turn"
        return {"output": {"message": {"role": "assistant", "content": content}},
                "stopReason": stop, "usage": {"inputTokens": 10, "outputTokens": 5}}


class Tests(unittest.TestCase):
    def test_citation_brackets_and_missing_source(self):
        for text in ("资料 [D1] 和 [D2]", "资料【D1】和【D2】"):
            self.assertTrue(all(evaluate("rag", text, []).values()))
        self.assertFalse(all(evaluate("rag", "资料【D1】", []).values()))

    def test_tool_rejects_unexpected_arguments(self):
        for use in [
            {"name": "delete_order", "input": {"order_id": "A100"}},
            {"name": "get_order", "input": {"order_id": "A100", "admin": True}},
            {"name": "get_order", "input": {"order_id": ["A100"]}},
        ]:
            self.assertFalse(execute_tool(use)[1])

    def test_json_type_validation(self):
        self.assertFalse(evaluate("extract",
            '{"order_id":"A100","total":true,"shipping_refund":15,"refund_approved":false}', [])[
                "JSON 与字段类型"])
        self.assertFalse(evaluate("extract", "[]", [])["JSON 与字段类型"])

    def test_tool_roundtrip_and_aggregated_usage(self):
        bench = Workbench.__new__(Workbench)
        bench.runtime = FakeRuntime()
        result = bench.run("test-model", "tools", "查询 A100", False)
        self.assertNotIn("error", result)
        self.assertEqual(result["usage"], {"inputTokens": 20, "outputTokens": 10})
        self.assertTrue(result["checks"]["成功执行查询工具"])
        returned = bench.runtime.calls[1]["messages"][2]["content"][0]["toolResult"]
        self.assertEqual(returned["toolUseId"], "t1")
        self.assertEqual(returned["status"], "success")


class ProtocolTests(unittest.TestCase):
    def test_http_model_not_found_keeps_error_and_explains_selected_endpoint(self):
        from unittest.mock import Mock
        for api in ("chat", "responses"):
            bench = self.bench(FakeRuntime())
            bench.openai_http = Mock()
            error = f'Bedrock {api} HTTP 404: {{"error":{{"code":"model_not_found"}}}}'
            bench.openai_http.invoke.side_effect = RuntimeError(error)
            result = bench.run("us.anthropic.claude-opus-4-8", "summary", "摘要", False, api=api)
            self.assertEqual(result["error"], error)
            self.assertIn(result["model"], result["errorHint"])
            self.assertIn(result["endpoint"], result["errorHint"])
            self.assertIn("Converse / InvokeModel", result["errorHint"])
            self.assertNotIn("checks", result)
            self.assertEqual(bench.openai_http.invoke.call_count, 1)
            self.assertEqual(bench.runtime.calls, [])

    def test_native_tool_reasoning_adaptation_is_scoped_and_preserves_override(self):
        for model, optimized, fields, expected in [
            ("us.openai.gpt-5.6-sol", True, {}, {"reasoning_effort": "none"}),
            ("us.openai.gpt-5.6-sol", False, {}, {}),
            ("us.openai.gpt-5.6-sol", True, {"reasoning_effort": "high"}, {"reasoning_effort": "high"}),
            ("us.openai.gpt-6-astra", True, {}, {}),
        ]:
            runtime = FakeRuntime()
            original = fields.copy()
            with patch("app.invoke", side_effect=lambda client, request: client.converse(**request)):
                result = self.bench(runtime).run(model, "tools", "查订单",
                                                optimized, fields, api="invoke")
            self.assertNotIn("error", result)
            self.assertEqual(result["requestFields"], expected)
            self.assertEqual(fields, original)
            self.assertEqual(runtime.calls[0].get("additionalModelRequestFields", {}), expected)

    def bench(self, runtime):
        bench = Workbench.__new__(Workbench)
        bench.runtime = runtime
        return bench

    def test_reasoning_preserved_across_tool_turn(self):
        class Signed(FakeRuntime):
            def converse(self, **kwargs):
                response = super().converse(**kwargs)
                if len(self.calls) == 1:
                    response['output']['message']['content'].insert(0, {'reasoningContent': {'reasoningText': {'text': 'private', 'signature': 'opaque-signature'}}})
                    response['output']['message']['content'].insert(1, {'reasoningContent': {'redactedContent': b'opaque'}})
                return response
        runtime = Signed()
        result = self.bench(runtime).run('m', 'thinking_tools', '查订单', False)
        self.assertNotIn('error', result)
        content = runtime.calls[1]['messages'][1]['content']
        self.assertEqual(content[0]['reasoningContent']['reasoningText']['signature'], 'opaque-signature')
        self.assertEqual(content[1]['reasoningContent']['redactedContent'], b'opaque')
        self.assertEqual(result['reasoningBlocks'], 2)
        self.assertNotIn('private', str(result))

    def test_multiple_tool_result_ids(self):
        class Multiple(FakeRuntime):
            def converse(self, **kwargs):
                response = super().converse(**kwargs)
                if len(self.calls) == 1:
                    response['output']['message']['content'].append({'toolUse': {'name': 'get_order', 'toolUseId': 't2', 'input': {'order_id': 'A200'}}})
                return response
        runtime = Multiple()
        result = self.bench(runtime).run('m', 'agent_parallel', '查询', False)
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual([b['toolResult']['toolUseId'] for b in runtime.calls[1]['messages'][2]['content']], ['t1', 't2'])

    def test_truncation_is_not_complete(self):
        class Truncated:
            def converse(self, **kwargs):
                return {'output': {'message': {'role': 'assistant', 'content': []}}, 'stopReason': 'max_tokens'}
        result = self.bench(Truncated()).run('m', 'truncation', '写', False)
        self.assertTrue(result['checks']['按预期触发输出上限（max_tokens）'])
        self.assertTrue(all(result['checks'].values()))
        ordinary = self.bench(Truncated()).run('m', 'summary', '写', False)
        self.assertFalse(ordinary['checks']['完整结束（end_turn）'])

    def test_stream_exception_keeps_partial_text_and_closes(self):
        class Events:
            closed = False
            def __iter__(self):
                return iter([{'contentBlockDelta': {'delta': {'text': 'partial'}}}, {'modelStreamErrorException': {'message': 'failed'}}])
            def close(self): self.closed = True
        class Streaming:
            events = Events()
            def converse_stream(self, **kwargs): return {'stream': self.events}
        runtime = Streaming()
        result = self.bench(runtime).run('m', 'stream', '写', False)
        self.assertIn('error', result)
        self.assertEqual(result['text'], 'partial')
        self.assertTrue(runtime.events.closed)

    def test_loop_is_bounded(self):
        class Loop:
            def converse(self, **kwargs):
                return {'output': {'message': {'role': 'assistant', 'content': [{'toolUse': {'name': 'get_order', 'toolUseId': 't', 'input': {'order_id': 'A100'}}}]}}, 'stopReason': 'tool_use'}
        result = self.bench(Loop()).run('m', 'tools', '查', False)
        self.assertIn('超过 6 轮', result['error'])
        self.assertEqual(len(result['trace']), 6)


if __name__ == "__main__":
    unittest.main()
