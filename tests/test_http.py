import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from app import make_handler


class HttpTests(unittest.TestCase):
    def test_auth_async_job_and_concurrency(self):
        release = threading.Event()
        class Bench:
            def catalog(self): return {'models': []}
            def validate(self, request):
                if not isinstance(request, dict): raise ValueError('object required')
            def compare(self, request):
                release.wait(5)
                return {'results': ['done']}
        with patch.dict(os.environ, {'DEMO_PASSWORD': 'test-password', 'DEMO_USERNAME': 'admin'}):
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(Bench()))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cookie = ""
        cookie_header = ""
        def request(path, body=None, auth=True):
            nonlocal cookie, cookie_header
            headers = {'Content-Type': 'application/json'}
            if auth: headers['Cookie'] = cookie
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}',
                data=json.dumps(body).encode() if body is not None else None, headers=headers)
            try: response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as exc: response = exc
            with response:
                if response.headers.get("Set-Cookie"):
                    cookie_header = response.headers["Set-Cookie"]
                    cookie = cookie_header.split(";", 1)[0]
                return response.status, json.load(response)
        try:
            self.assertEqual(request('/api/health', auth=False)[0], 200)
            self.assertEqual(request('/api/catalog', auth=False)[0], 401)
            self.assertEqual(request('/api/login', {'username': 'admin', 'password': 'wrong'})[0], 401)
            self.assertEqual(request('/api/login', {'username': 'wrong', 'password': 'test-password'})[0], 401)
            self.assertEqual(request('/api/login', [])[0], 400)
            self.assertEqual(request('/api/login', {'username': 'admin', 'password': 'test-password'})[0], 200)
            for attribute in ['HttpOnly', 'Secure', 'SameSite=Strict', 'Max-Age=28800']:
                self.assertIn(attribute, cookie_header)
            self.assertEqual(request('/api/session')[1], {'username': 'admin'})
            self.assertEqual(request('/api/compare', [], True)[0], 400)
            status, job = request('/api/compare', {})
            self.assertEqual(status, 202)
            self.assertEqual(request('/api/compare', {})[0], 429)
            self.assertEqual(request('/api/jobs/' + job['id'])[1]['status'], 'running')
            release.set()
            for _ in range(100):
                result = request('/api/jobs/' + job['id'])[1]
                if result['status'] == 'completed': break
                time.sleep(.01)
            self.assertEqual(result['report']['results'], ['done'])
            self.assertEqual(request('/api/compare', {})[0], 202)
            old_cookie = cookie
            self.assertEqual(request('/api/logout', {})[0], 200)
            self.assertIn('Max-Age=0', cookie_header)
            cookie = old_cookie
            self.assertEqual(request('/api/catalog')[0], 401)
            for _ in range(20):
                status, _ = request('/api/login', {'username': 'admin', 'password': 'wrong'})
            self.assertEqual(status, 429)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join()
