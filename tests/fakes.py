"""Stand-ins for the YouTube API client. Nothing here touches the network."""

import json

import httplib2
from googleapiclient.errors import HttpError


def make_http_error(status, reason):
    """An HttpError shaped like the ones the Data API actually returns."""
    response = httplib2.Response({"status": status})
    content = json.dumps(
        {"error": {"code": status, "message": reason, "errors": [{"reason": reason}]}}
    ).encode("utf-8")
    return HttpError(response, content)


class FakeRequest:
    """Stands in for a googleapiclient HttpRequest."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.num_retries = None

    def execute(self, num_retries=0):
        self.num_retries = num_retries
        if self.error:
            raise self.error
        return self.payload


class FakeResource:
    """One API resource (search, videos, commentThreads).

    Answers successive list() calls from a queue of responses; an exception in
    the queue is raised by that request's execute(). Every call's parameters
    are recorded in `calls`.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def list(self, **params):
        self.calls.append(params)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            return FakeRequest(error=response)
        return FakeRequest(payload=response)


class FakeYoutubeClient:
    def __init__(self, search=None, videos=None, comment_threads=None):
        self._search = search
        self._videos = videos
        self._comment_threads = comment_threads

    def search(self):
        return self._search

    def videos(self):
        return self._videos

    def commentThreads(self):
        return self._comment_threads
