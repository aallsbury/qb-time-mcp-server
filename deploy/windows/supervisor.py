"""Supervise only QBTime. --check does not start a listener or contact the API."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import threading

from probe import probe


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    for key in ('repoRoot', 'python', 'node', 'gateway', 'envFile', 'stateDirectory'):
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f'{key} must be an absolute path')
        if any(char in value for char in '\n\r"&|<>^%!'):
            raise ValueError(f'{key} contains shell control characters')
    for key in ('python', 'node', 'gateway', 'envFile'):
        if not Path(config[key]).is_file():
            raise ValueError(f'{key} does not exist')
    for name in ('main.py', 'config.py', 'tests/fixtures/deployed-tool-contract.json'):
        if not (Path(config['repoRoot']) / name).is_file():
            raise ValueError(f'Release is incomplete: {name}')
    gateway_manifest = Path(config['gateway']).parents[1] / 'package.json'
    installed_gateway = json.loads(gateway_manifest.read_text(encoding='utf-8'))
    if installed_gateway.get('name') != 'supergateway' or installed_gateway.get('version') != config['gatewayVersion']:
        raise ValueError('Gateway version differs from the reviewed release')
    if not isinstance(config['account'], str) or '\\' not in config['account']:
        raise ValueError('account must be an explicit DOMAIN\\user')
    bounds = {'port': (1, 65535), 'startupTimeoutSeconds': (10, 180),
              'probeIntervalSeconds': (5, 300), 'maxConsecutiveFailures': (1, 10),
              'stableResetSeconds': (60, 3600), 'cooldownSeconds': (1, 3600)}
    for key, (low, high) in bounds.items():
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f'{key} outside allowed range')
    delays = config['restartDelaysSeconds']
    if not isinstance(delays, list) or not delays or any(type(n) is not int or not 1 <= n <= 300 for n in delays):
        raise ValueError('Restart delays must be bounded positive seconds')
    return config


def gateway_command(config):
    # Quote the stdio command paths for Windows and reject shell metacharacters;
    # load_config rejects cmd expansion/metacharacters and credentials are never arguments.
    stdio = ' '.join('"' + value + '"' for value in (
        config['python'], str(Path(config['repoRoot']) / 'main.py'),
        '--env-file', config['envFile']))
    return [config['node'], config['gateway'], '--port', str(config['port']),
            '--stdio', stdio, '--ssePath', '/sse', '--messagePath', '/message',
            '--healthEndpoint', '/healthz', '--logLevel', 'info']


class InstanceLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        import msvcrt
        self.file = open(self.path, 'a+b')
        try:
            # Windows permits locking beyond EOF. A duplicate owner must not
            # read an already locked byte before entering this guarded block.
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise RuntimeError('Another QBTime supervisor owns the lock')
        return self

    def __exit__(self, *_):
        import msvcrt
        self.file.seek(0)
        msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()


class ProcessTree:
    """Windows Job Object: closing the supervisor kills only its own child tree."""
    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                        ('max_ws', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', Io), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def write_status(directory, **values):
    values['utc'] = datetime.now(timezone.utc).isoformat()
    temporary = directory / 'status.tmp'
    temporary.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')
    temporary.replace(directory / 'status.json')


def capture_errors(pipe, logger):
    # Info-level request/results go to DEVNULL. Retain only recognized
    # application metadata, never arbitrary provider responses or RPC payloads.
    import re
    with pipe:
        for line in iter(lambda: pipe.readline(1024), b''):
            text = line[:1024].decode('utf-8', errors='replace')
            if not text.strip():
                continue
            # The gateway forwards Python logging through stderr even for INFO.
            # Keep the severity without retaining the original message or payload.
            if ' - INFO - ' in text:
                logger.info('application informational message')
                continue
            category = re.search(r'category=([A-Za-z]+)', text)
            status = re.search(r'status=([0-9]{3})', text)
            if category or status or ' - ERROR - ' in text or 'Traceback (' in text:
                logger.error('gateway stderr category=%s status=%s',
                             category.group(1) if category else 'child-diagnostic',
                             status.group(1) if status else 'unknown')
            else:
                logger.warning('unclassified gateway diagnostic; payload omitted')


def supervise(config, config_path):
    if os.name != 'nt':
        raise RuntimeError('This supervisor is for Windows')
    account = subprocess.check_output(['whoami'], text=True).strip()
    if account.casefold() != config['account'].casefold():
        raise ValueError('Run the supervisor as the configured account')
    state = Path(config['stateDirectory'])
    state.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(state / 'supervisor.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger = logging.getLogger('qbtime-supervisor')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    contract = json.loads((Path(config['repoRoot']) / 'tests/fixtures/deployed-tool-contract.json').read_text())
    names = [tool['name'] for tool in contract['tools']]
    failures = 0
    with InstanceLock(state / f"port-{config['port']}.lock"):
        while True:
            try:
                with socket.create_connection(('127.0.0.1', config['port']), timeout=.5):
                    raise RuntimeError('Port already has a listener; refusing duplicate ownership')
            except (ConnectionRefusedError, TimeoutError):
                pass
            job, child = ProcessTree(), None
            started = time.monotonic()
            ready = False
            try:
                environment = os.environ.copy()
                # The gateway starts one stdio process per session. Aggregate
                # metadata in this process, avoiding multiprocess file rotation.
                environment.pop('QBT_LOG_FILE', None)
                # Child waits for G on stdin until its job assignment is complete.
                # No gateway/grandchild can escape the job during launch.
                child = subprocess.Popen([config['python'], str(Path(__file__).resolve()), '--child', '--config', str(config_path)],
                                         cwd=config['repoRoot'], env=environment, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                threading.Thread(target=capture_errors, args=(child.stderr, logger), daemon=True).start()
                job.assign(child)
                child.stdin.write(b'G')
                child.stdin.flush()
                # The released gateway treats stdin EOF as shutdown. Keep the
                # pipe alive for the owned launcher's lifetime after releasing it.
                logger.info('started supervised gateway launcher pid=%s', child.pid)
                write_status(state, state='starting', launcherPid=child.pid, consecutiveFailures=failures)
                bad_probes = 0
                while child.poll() is None:
                    try:
                        result = probe(config['port'], names)
                        ready = True
                        bad_probes = 0
                        write_status(state, state='ready', launcherPid=child.pid, **result)
                    except Exception as exc:
                        bad_probes += 1
                        logger.warning('readiness failed category=%s count=%s', type(exc).__name__, bad_probes)
                        if (ready and bad_probes >= 3) or (not ready and time.monotonic() - started >= config['startupTimeoutSeconds']):
                            break
                    # Do not hide process exits behind the deliberately slow
                    # full MCP readiness interval.
                    try:
                        child.wait(timeout=config['probeIntervalSeconds'] if ready else 2)
                    except subprocess.TimeoutExpired:
                        pass
                if ready and time.monotonic() - started >= config['stableResetSeconds']:
                    failures = 0
                logger.warning('gateway stopped or failed readiness exitCode=%s', child.poll())
            finally:
                job.close()
                if child is not None:
                    if child.stdin and not child.stdin.closed:
                        child.stdin.close()
                    # Also terminate the blocked launcher if job assignment itself failed.
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=10)
            failures += 1
            write_status(state, state='retrying', consecutiveFailures=failures)
            if failures >= config['maxConsecutiveFailures']:
                write_status(state, state='cooldown', consecutiveFailures=failures)
                logger.warning('retry batch exhausted; cooling down for %s seconds', config['cooldownSeconds'])
                time.sleep(config['cooldownSeconds'])
                failures = 0
            else:
                delay = config['restartDelaysSeconds'][min(failures - 1, len(config['restartDelaysSeconds']) - 1)]
                logger.warning('retrying after %s seconds', delay)
                time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.check:
            print(json.dumps({'ok': True, 'account': config['account'], 'port': config['port'], 'startsListener': False}))
            return 0
        if args.child:
            if sys.stdin.buffer.read(1) != b'G':
                return 2
            return subprocess.call(gateway_command(config), cwd=config['repoRoot'])
        return supervise(config, args.config.resolve())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.getLogger('qbtime-supervisor').error('supervisor stopped category=%s', type(exc).__name__)
        print(json.dumps({'ok': False, 'errorCategory': type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
