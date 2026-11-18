"""Public MCP diagnostics must never contain request or upstream payloads."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import api
import main
import server


CANARY = 'private-test-marker'
TOKEN = 'example-credential-for-unit-test'


def response(status):
    reply = requests.Response()
    reply.status_code = status
    reply.url = 'https://example.invalid/?worker=' + CANARY
    reply.reason = CANARY
    reply._content = json.dumps({'error': {'message': CANARY + TOKEN}}).encode()
    reply._content_consumed = True
    return reply


class DiagnosticPrivacyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {'QBT_UPSTREAM_STATE': str(Path(tmp.name) / 'state.db')}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        with patch.object(api.QuickBooksTimeAPI, 'validate_token', return_value=True):
            self.rpc = server.JSONRPCServer(TOKEN, 'test')

    def assert_private(self, text):
        self.assertNotIn(CANARY, text)
        self.assertNotIn(TOKEN, text)

    def call(self, name, arguments):
        request = {'id': 'correlation', 'jsonrpc': '2.0', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': arguments}}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.rpc.handle_message(json.dumps(request))
        self.assert_private(output.getvalue())
        reply = json.loads(output.getvalue())
        self.assertEqual(reply['id'], 'correlation')
        self.assertEqual(reply['error']['code'], -32601 if name == CANARY else -32000)
        return reply['error']['message']

    def test_http_rejection_omits_body_reason_and_url_from_tool_and_startup(self):
        reply = response(403)
        with patch.object(requests, 'get', return_value=reply), patch.object(reply, 'json') as read_body:
            with self.assertLogs(level='ERROR') as logs:
                message = self.call('get_jobcodes', {'name': CANARY})
                with self.assertRaisesRegex(ValueError, '403') as error:
                    self.rpc.api.validate_token()
            read_body.assert_not_called()
        self.assertIn('403', message)
        self.assertIn('permissions', message)
        self.assert_private(str(error.exception))
        self.assert_private('\n'.join(logs.output))
        self.assertTrue(any('stage=startup status=403' in item for item in logs.output))

    def test_retry_after_remains_actionable_across_calls_without_echoing_header(self):
        reply = response(429)
        reply.headers['Retry-After'] = CANARY
        with patch.object(requests, 'get', return_value=reply) as get, self.assertLogs(level='ERROR') as logs:
            for _ in range(2):
                self.assertRegex(self.call('get_current_user', {}), r'429.*Retry after [0-9]+ seconds')
            get.assert_called_once()
        self.assert_private('\n'.join(logs.output))

    def test_invalid_json_response_excludes_private_document_text(self):
        reply = response(200)
        reply._content = (CANARY + TOKEN).encode()
        with patch.object(requests, 'get', return_value=reply), self.assertLogs(level='ERROR') as logs:
            self.assertIn('invalid JSON', self.call('get_current_user', {}))
        self.assert_private('\n'.join(logs.output))

    def test_transport_and_unexpected_errors_do_not_expose_exception_text(self):
        # HTTP connection failures can carry the full query URL.
        with patch.object(requests, 'get', side_effect=requests.ConnectionError(CANARY + TOKEN)):
            with self.assertLogs(level='ERROR') as logs:
                self.assertIn('connectivity', self.call('get_jobcodes', {'name': CANARY}))
            self.assert_private('\n'.join(logs.output))
        with patch.object(self.rpc.api, 'get_current_user', side_effect=ValueError(CANARY + TOKEN)):
            with self.assertLogs(level='ERROR') as logs:
                self.assertIn('service logs', self.call('get_current_user', {}))
            self.assert_private('\n'.join(logs.output))

    def test_validation_identifies_fields_and_allowed_values_without_echo(self):
        examples = [
            ('get_jobcodes', {'active': CANARY}, 'active must be one of'),
            ('get_project_activities', {'activity_types': [CANARY]}, 'activity_types'),
            ('get_notifications', {'notification_types': [CANARY]}, 'Notification types'),
            ('get_last_modified', {'types': [CANARY]}, 'Entity types'),
        ]
        with patch.object(requests, 'get') as get, self.assertLogs(level='ERROR') as logs:
            for name, arguments, expected in examples:
                with self.subTest(name=name):
                    self.assertIn(expected, self.call(name, arguments))
            get.assert_not_called()
        self.assert_private('\n'.join(logs.output))

    def test_unknown_tool_and_notification_omit_supplied_method(self):
        self.assertIn('tools/list', self.call(CANARY, {}))
        with self.assertLogs(level='INFO') as logs:
            self.rpc.handle_message(json.dumps({'jsonrpc': '2.0', 'method': CANARY}))
        self.assert_private('\n'.join(logs.output))

    def test_startup_omits_unexpected_failure_details(self):
        with patch.dict(os.environ, {'QB_TIME_ACCESS_TOKEN': TOKEN}), patch.object(main, 'load_dotenv'):
            with patch.object(server, 'run_server', side_effect=OSError(CANARY + TOKEN)):
                with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertLogs(level='ERROR') as logs:
                    self.assertEqual(main.main([]), 1)
        self.assert_private(stderr.getvalue() + '\n'.join(logs.output))
