"""Fake HTTP session for Home Assistant client tests."""


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class RecordingHttpSession:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        return self._record("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._record("POST", url, kwargs)

    def _record(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response
