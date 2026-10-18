import logging

import pytest

import src.utils.api as api
from src.utils.logger import EXTRACTION_LOGGER_NAME

from fakes import FakeYoutubeClient


@pytest.fixture(autouse=True)
def no_shared_client(monkeypatch):
    """Every test starts without a client, and none leaks into the next."""
    monkeypatch.setattr(api, "_youtube_client", None)


@pytest.fixture
def install_client(monkeypatch):
    """Installs a FakeYoutubeClient as the shared client and returns it."""

    def install(**resources):
        client = FakeYoutubeClient(**resources)
        monkeypatch.setattr(api, "_youtube_client", client)
        return client

    return install


@pytest.fixture
def extraction_logger():
    """Yields the extraction logger and strips any handlers a test attached."""
    logger = logging.getLogger(EXTRACTION_LOGGER_NAME)
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
