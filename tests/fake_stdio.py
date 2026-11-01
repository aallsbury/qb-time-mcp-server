"""Synthetic child used only by integration tests; no HTTP/API actions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class FakeAPI:
    def __init__(self, *_):
        self.access_token = 'synthetic-token'

    def __getattr__(self, name):
        return lambda args=None: {'fixture': name, 'arguments': args}


server.QuickBooksTimeAPI = FakeAPI
server.run_server('synthetic-token', 'test')
