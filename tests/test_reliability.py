import contextlib
from concurrent.futures import ThreadPoolExecutor
import ctypes
import io
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'deploy/windows'))
import api
import config
import main
import server
from supervisor import InstanceLock, ProcessTree, capture_errors, gateway_command
from probe import probe

CONTRACT = json.loads((ROOT / 'tests/fixtures/deployed-tool-contract.json').read_text())


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else {'results': {'fixture': True}}
        self.error = error
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.closed = True
    def raise_for_status(self):
        if self.error:
            raise self.error
    def json(self):
        return self.payload


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.api_patch = patch.object(server, 'QuickBooksTimeAPI')
        self.fake = self.api_patch.start().return_value
        self.addCleanup(self.api_patch.stop)
        self.rpc = server.JSONRPCServer('synthetic-token', 'test')
    def request(self, method, params=None):
        body = {'jsonrpc': '2.0', 'id': 'contract', 'method': method}
        if params is not None:
            body['params'] = params
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.rpc.handle_message(json.dumps(body))
        return json.loads(output.getvalue())
    def test_initialize_and_tools_preserve_deployed_contract(self):
        self.assertEqual(self.request('initialize')['result']['serverInfo'], CONTRACT)
        self.assertEqual(self.request('tools/list')['result']['tools'], CONTRACT['tools'])
        self.assertEqual(self.request('ping')['result'], {})
    def test_all_twenty_tools_preserve_content_result_envelope(self):
        for tool in CONTRACT['tools']:
            with self.subTest(tool=tool['name']):
                payload = {'results': {'fixture': tool['name']}}
                getattr(self.fake, tool['name']).return_value = payload
                result = self.request('tools/call', {'name': tool['name'], 'arguments': {}})
                self.assertEqual(json.loads(result['result']['content'][0]['text']), payload)
                getattr(self.fake, tool['name']).assert_called_once_with({})
    def test_malformed_input_does_not_kill_next_request(self):
        for raw in ('[]', 'null', '1', '{broken'):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.rpc.handle_message(raw)
            self.assertIn('error', json.loads(output.getvalue()))
        self.assertEqual(self.request('tools/call', [])['error']['code'], -32602)
        self.assertEqual(self.request('tools/call', {'name': ['bad'], 'arguments': {}})['error']['code'], -32602)
        self.assertEqual(self.request('ping')['result'], {})


class HttpTests(unittest.TestCase):
    def test_get_and_post_have_deadlines_and_close_responses(self):
        client = api.BaseAPI('synthetic-token')
        for method in ('GET', 'POST'):
            response = FakeResponse()
            with patch.object(requests, method.lower(), return_value=response) as send:
                self.assertEqual(client.make_request('fixture', method=method), response.payload)
                self.assertEqual(send.call_args.kwargs['timeout'], (5.0, 30.0))
                self.assertTrue(response.closed)
    def test_response_closes_on_error(self):
        response = FakeResponse(error=requests.HTTPError('synthetic failure'))
        with patch.object(requests, 'get', return_value=response):
            with self.assertRaises(ValueError):
                api.BaseAPI('synthetic-token').make_request('fixture')
        self.assertTrue(response.closed)
    def test_token_validation_has_deadline_and_closes(self):
        response = FakeResponse()
        with patch.object(requests, 'get', return_value=response) as send:
            api.QuickBooksTimeAPI('synthetic-token')
        self.assertEqual(send.call_args.kwargs['timeout'], (5.0, 30.0))
        self.assertTrue(response.closed)
    def test_existing_current_totals_post_behavior_is_preserved(self):
        client = api.ReportsAPI('synthetic-token')
        with patch.object(client, 'make_request', return_value={}) as send:
            client.get_current_totals({'user_ids': [101, 102], 'on_the_clock': 'yes'})
        self.assertEqual(send.call_args.kwargs['method'], 'POST')
        self.assertEqual(send.call_args.kwargs['data'], {'data': {'user_ids': '101,102', 'on_the_clock': 'yes'}})
    def test_bad_timeout_configuration_fails_closed(self):
        for value in ('0', '-1', 'nan', 'inf', '121', 'bad'):
            with patch.dict(os.environ, {'QBT_READ_TIMEOUT_SECONDS': value}):
                with self.assertRaises(ValueError):
                    config.request_timeout()
    def test_config_check_never_constructs_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / '.env'
            env.write_text('QB_TIME_ACCESS_TOKEN=synthetic-config-token\n')
            with patch.dict(os.environ, {}, clear=True), patch.object(server, 'run_server') as run:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main.main(['--env-file', str(env), '--check-config']), 0)
                self.assertTrue(json.loads(output.getvalue())['ok'])
                self.assertNotIn('synthetic-config-token', output.getvalue())
                run.assert_not_called()


@unittest.skipUnless(os.name == 'nt', 'Windows ownership tests')
class OwnershipTests(unittest.TestCase):
    def test_child_logs_reduce_payloads_to_metadata(self):
        logger = unittest.mock.Mock()
        capture_errors(io.BytesIO(b'category=ValueError status=401 synthetic-secret employee-payload\n'), logger)
        self.assertEqual(logger.error.call_args.args, ('gateway stderr category=%s status=%s', 'ValueError', '401'))
    def test_info_and_blank_stderr_are_not_reported_as_errors(self):
        logger = unittest.mock.Mock()
        capture_errors(io.BytesIO(b'\r\n[supergateway] Child stderr: 2026-01-01 - INFO - synthetic-secret\n\n'), logger)
        logger.info.assert_called_once_with('application informational message')
        logger.error.assert_not_called()
        logger.warning.assert_not_called()
    def test_unclassified_stderr_is_warning_without_payload(self):
        logger = unittest.mock.Mock()
        capture_errors(io.BytesIO(b'unclassified synthetic-secret\n'), logger)
        logger.warning.assert_called_once_with('unclassified gateway diagnostic; payload omitted')
        logger.error.assert_not_called()
    def test_duplicate_supervisor_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with InstanceLock(Path(tmp) / 'lock'):
                with self.assertRaises(RuntimeError):
                    with InstanceLock(Path(tmp) / 'lock'):
                        self.fail('duplicate lock accepted')
            with InstanceLock(Path(tmp) / 'lock'):
                pass
    def test_job_close_kills_owned_child_tree(self):
        code = 'import sys,subprocess,time;sys.stdin.buffer.read(1);p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);print(p.pid,flush=True);time.sleep(60)'
        child = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        job = ProcessTree()
        try:
            job.assign(child)
            child.stdin.write(b'G'); child.stdin.close()
            descendant = int(child.stdout.readline())
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x00100000, False, descendant)
            self.assertTrue(handle)
            job.close()
            child.wait(timeout=5)
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)
        finally:
            job.close()
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            child.stdout.close()
    def test_real_supervisor_recovers_only_its_synthetic_child(self):
        gateway_root = os.environ.get('QBT_TEST_GATEWAY_ROOT')
        if not gateway_root:
            self.skipTest('Set QBT_TEST_GATEWAY_ROOT for complete supervision test')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'tests/fixtures').mkdir(parents=True)
            (root / 'tests/fixtures/deployed-tool-contract.json').write_text(json.dumps(CONTRACT))
            source = (ROOT / 'tests/fake_stdio.py').read_text().replace('str(Path(__file__).resolve().parents[1])', repr(str(ROOT)))
            (root / 'main.py').write_text(source)
            (root / 'config.py').write_text('# Synthetic release marker\n')
            (root / 'synthetic.env').write_text('QB_TIME_ACCESS_TOKEN=synthetic-token\n')
            gateway = Path(gateway_root) / 'node_modules/supergateway/dist/index.js'
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            config = {'account': subprocess.check_output(['whoami'], text=True).strip(),
                      'repoRoot': str(root), 'python': sys.executable, 'node': shutil.which('node'),
                      'gateway': str(gateway), 'gatewayVersion': '4.2.1', 'envFile': str(root / 'synthetic.env'),
                      'stateDirectory': str(root / 'state'), 'port': port, 'startupTimeoutSeconds': 10,
                      'probeIntervalSeconds': 300, 'maxConsecutiveFailures': 1, 'cooldownSeconds': 1,
                      'stableResetSeconds': 60, 'restartDelaysSeconds': [1]}
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            owner = subprocess.Popen([sys.executable, str(ROOT / 'deploy/windows/supervisor.py'), '--config', str(config_path)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            cleanup_job = ProcessTree()
            cleanup_job.assign(owner)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            def ready(previous=None):
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    try:
                        status = json.loads((root / 'state/status.json').read_text())
                        if status['state'] == 'ready' and status['launcherPid'] != previous:
                            return status['launcherPid']
                    except (OSError, ValueError):
                        pass
                    if owner.poll() is not None:
                        log = root / 'state/supervisor.log'
                        self.fail('Synthetic supervisor exited before readiness: ' + (log.read_text()[-2500:] if log.exists() else 'no log'))
                    time.sleep(.1)
                self.fail('Synthetic supervisor did not reach readiness')
            handle = None
            try:
                first = ready()
                handle = kernel.OpenProcess(0x0001 | 0x00100000, False, first)
                self.assertTrue(handle)
                self.assertTrue(kernel.TerminateProcess(handle, 71))
                kernel.CloseHandle(handle)
                handle = None
                recovery_started = time.monotonic()
                second = ready(first)
                self.assertLess(time.monotonic() - recovery_started, 25, 'Exit recovery waited for the 300-second probe interval')
                handle = kernel.OpenProcess(0x00100000, False, second)
                self.assertTrue(handle)
                owner.kill()
                owner.wait(timeout=10)
                self.assertEqual(kernel.WaitForSingleObject(handle, 10000), 0)
            finally:
                if handle: kernel.CloseHandle(handle)
                cleanup_job.close()
                if owner.poll() is None: owner.kill()
                owner.wait(timeout=10)


class SseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gateway = Path(os.environ.get('QBT_TEST_GATEWAY_ROOT', ROOT / 'deploy/gateway')) / 'node_modules/supergateway/dist/index.js'
        if not gateway.is_file():
            raise unittest.SkipTest('Run npm ci in deploy/gateway for SSE integration')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            cls.port = reservation.getsockname()[1]
        stdio = f'"{sys.executable}" "{ROOT / "tests/fake_stdio.py"}"'
        command = ['node', str(gateway), '--port', str(cls.port), '--stdio', stdio, '--logLevel', 'none']
        cls.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        cls.job = ProcessTree() if os.name == 'nt' else None
        cls.addClassCleanup(cls.cleanup_gateway)
        if cls.job:
            cls.job.assign(cls.process)
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=.1):
                    return
            except OSError:
                if cls.process.poll() is not None:
                    raise RuntimeError('Synthetic SSE gateway exited')
                time.sleep(.1)
        raise RuntimeError('Synthetic SSE gateway did not bind its ephemeral test port')
    @classmethod
    def cleanup_gateway(cls):
        if cls.job:
            cls.job.close()
        elif cls.process.poll() is None:
            cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stderr.close()
    def test_readiness_handshake_and_contract_without_business_calls(self):
        for _ in range(3):
            self.assertEqual(probe(self.port, [t['name'] for t in CONTRACT['tools']]), {'ok': True, 'toolCount': 20})
    def test_concurrent_sse_sessions_and_reconnect(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: probe(self.port, [t['name'] for t in CONTRACT['tools']]), range(4)))
        self.assertEqual(results, [{'ok': True, 'toolCount': 20}] * 4)
        self.assertIsNone(self.process.poll())
        self.assertEqual(probe(self.port)['toolCount'], 20)
    def test_sse_forwards_full_schemas_and_synthetic_results(self):
        base = f'http://127.0.0.1:{self.port}'
        with requests.Session() as session, session.get(base + '/sse', stream=True, timeout=(2, 3)) as response:
            lines = response.iter_lines(chunk_size=1, decode_unicode=True)
            def event():
                data = []
                for line in lines:
                    if not line and data:
                        return '\n'.join(data)
                    if line.startswith('data:'):
                        data.append(line[5:].lstrip())
                raise RuntimeError('Unexpected SSE EOF')
            endpoint = urljoin(base, event())
            def call(number, method, params=None):
                body = {'jsonrpc': '2.0', 'id': number, 'method': method}
                if params is not None: body['params'] = params
                with session.post(endpoint, json=body, timeout=(2, 3)) as sent: sent.raise_for_status()
                while True:
                    data = json.loads(event())
                    if data.get('id') == number: return data
            self.assertEqual(call(1, 'initialize')['result']['serverInfo'], CONTRACT)
            self.assertEqual(call(2, 'tools/list')['result']['tools'], CONTRACT['tools'])
            for index, tool in enumerate(CONTRACT['tools'], 3):
                result = call(index, 'tools/call', {'name': tool['name'], 'arguments': {'synthetic': True}})
                self.assertEqual(json.loads(result['result']['content'][0]['text']), {'fixture': tool['name'], 'arguments': {'synthetic': True}})


if __name__ == '__main__':
    unittest.main()
