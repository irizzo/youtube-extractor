import json

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# googleapiclient retries 5xx, 429 and rate-limit 403s on its own, with
# randomized exponential backoff, as long as num_retries is set.
DEFAULT_NUM_RETRIES = 3

# 403s that mean the daily allowance is gone. These are never retried by the
# client and never recover within the same run.
FATAL_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}


_youtube_client = None


def init_youtube_client(search_config):
    """Builds the YouTube client for this run from an already-validated config.

    Call once, from whatever composes the run: main(), a notebook, or a test.
    This module never reads the config itself, so no extraction step can pick
    up credentials behind the caller's back.
    """

    global _youtube_client

    _youtube_client = build(
        "youtube", "v3", developerKey=search_config["youtube_api_key"]
    )

    return _youtube_client


def get_youtube_client():
    """Returns the client built by init_youtube_client().

    Raises RuntimeError if the caller never initialised one, rather than
    quietly reaching for a global config.
    """

    if _youtube_client is None:
        raise RuntimeError(
            "YouTube client not initialised. Call "
            "init_youtube_client(search_config) before running an extraction step."
        )

    return _youtube_client


def reset_youtube_client():
    """Drops the current client. Mainly useful for tests and notebooks."""

    global _youtube_client

    _youtube_client = None


class QuotaExceededError(Exception):
    """Raised when the daily YouTube API quota is exhausted.

    Deliberately not an HttpError subclass: the comments stage swallows
    HttpError to skip individual videos, and quota exhaustion must travel
    past that handler to stop the whole run.
    """


def get_error_reasons(error):
    """Extracts the machine-readable reason codes from an HttpError payload."""

    try:
        payload = json.loads(error.content.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return set()

    if not isinstance(payload, dict):
        return set()

    errors = payload.get("error", {}).get("errors", [])
    if not isinstance(errors, list):
        return set()

    return {item.get("reason", "") for item in errors if isinstance(item, dict)}


def is_quota_exhausted(error):
    """True if the error means the daily quota is spent, not merely throttled."""

    if error.status_code != 403:
        return False

    if get_error_reasons(error) & FATAL_QUOTA_REASONS:
        return True

    # Some 403s arrive without a parseable reason list; fall back to the message.
    return "quota" in str(error).lower()


def execute_request(request, description, num_retries=DEFAULT_NUM_RETRIES):
    """
    Executes a Google API request, retrying transient failures.

    Transient errors (5xx, 429, rate limiting) are retried by the client.
    An exhausted daily quota is re-raised as QuotaExceededError so callers
    can stop the run instead of treating it as a per-item failure. Every
    other HttpError propagates unchanged, for the caller to handle.
    """

    try:
        return request.execute(num_retries=num_retries)
    except HttpError as error:
        if is_quota_exhausted(error):
            raise QuotaExceededError(
                f"Daily YouTube API quota exhausted during {description}."
            ) from error
        raise
