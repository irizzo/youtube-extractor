import httplib2
import pytest
from googleapiclient.errors import HttpError

import src.utils.api as api
from src.extraction import yt_comments_retrieval, yt_videos_retrieval
from src.utils.api import QuotaExceededError, execute_request, is_quota_exhausted

from fakes import FakeRequest, make_http_error


@pytest.mark.parametrize(
    "status, reason, fatal",
    [
        (403, "quotaExceeded", True),
        (403, "dailyLimitExceeded", True),
        (403, "rateLimitExceeded", False),
        (403, "userRateLimitExceeded", False),
        (403, "commentsDisabled", False),
        (404, "videoNotFound", False),
        (500, "backendError", False),
    ],
)
def test_is_quota_exhausted_classifies_reasons(status, reason, fatal):
    assert is_quota_exhausted(make_http_error(status, reason)) is fatal


@pytest.mark.parametrize(
    "body, fatal",
    [(b"Daily quota spent", True), (b"Forbidden", False)],
    ids=["mentions quota", "no quota"],
)
def test_is_quota_exhausted_falls_back_to_the_message(body, fatal):
    error = HttpError(httplib2.Response({"status": 403}), body)

    assert is_quota_exhausted(error) is fatal


def test_execute_request_translates_quota_exhaustion():
    request = FakeRequest(error=make_http_error(403, "quotaExceeded"))

    with pytest.raises(QuotaExceededError, match="search.list") as caught:
        execute_request(request, "search.list")

    assert isinstance(caught.value.__cause__, HttpError)


def test_execute_request_lets_other_http_errors_through():
    request = FakeRequest(error=make_http_error(404, "videoNotFound"))

    with pytest.raises(HttpError):
        execute_request(request, "videos.list")


def test_execute_request_returns_the_payload_and_asks_for_retries():
    request = FakeRequest(payload={"items": [1, 2]})

    assert execute_request(request, "search.list") == {"items": [1, 2]}
    assert request.num_retries == api.DEFAULT_NUM_RETRIES == 3


def test_quota_error_escapes_http_error_handlers():
    # The comments stage catches HttpError to skip one video. Quota exhaustion
    # must pass that handler, or every remaining video gets checkpointed empty.
    assert not issubclass(QuotaExceededError, HttpError)


def test_get_client_before_init_names_the_fix():
    with pytest.raises(RuntimeError, match="init_youtube_client"):
        api.get_youtube_client()


def test_init_builds_one_client_every_step_shares():
    client = api.init_youtube_client({"youtube_api_key": "test-key"})

    assert api.get_youtube_client() is client
    assert yt_videos_retrieval.get_youtube_client() is client
    assert yt_comments_retrieval.get_youtube_client() is client


def test_reset_then_reinit_replaces_the_client():
    first = api.init_youtube_client({"youtube_api_key": "key-1"})

    api.reset_youtube_client()
    with pytest.raises(RuntimeError):
        api.get_youtube_client()

    second = api.init_youtube_client({"youtube_api_key": "key-2"})
    assert second is not first
    assert api.get_youtube_client() is second
