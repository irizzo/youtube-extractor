import pytest

from src.extraction import yt_videos_retrieval as videos
from src.extraction.yt_videos_retrieval import (
    filter_videos,
    get_batched_video_details,
    is_short_video,
    process_and_filter_batch,
    youtube_video_search_gen,
)
from src.utils.api import QuotaExceededError

from fakes import FakeResource, make_http_error


def search_page(video_ids, next_token=None):
    page = {
        "items": [
            {
                "id": {"videoId": video_id},
                "snippet": {
                    "title": f"title {video_id}",
                    "description": "snippet description",
                    "publishedAt": "2026-01-01T00:00:00Z",
                    "channelTitle": "Canal",
                    "channelId": "c1",
                },
            }
            for video_id in video_ids
        ]
    }
    if next_token:
        page["nextPageToken"] = next_token
    return page


def video(video_id, title=None):
    return {
        "video_id": video_id,
        "video_title": title or f"title {video_id}",
        "channel_id": "c1",
    }


DETAILS = {
    "short": {"full_description": "tiny", "duration": "PT1M30S"},
    "long": {"full_description": "a proper description", "duration": "PT12M"},
    "tagged": {"full_description": "Assista! #Shorts", "duration": "PT12M"},
    "no_desc": {"full_description": "", "duration": "PT12M"},
}


@pytest.fixture
def details(monkeypatch):
    """videos.list stub: answers from DETAILS and, like the real endpoint,
    silently omits IDs it cannot serve."""
    monkeypatch.setattr(
        videos,
        "get_batched_video_details",
        lambda ids: {i: DETAILS[i] for i in ids if i in DETAILS},
    )


def ids_of(records):
    return sorted(r["video_id"] for r in records)


# --- is_short_video ---------------------------------------------------------


@pytest.mark.parametrize(
    "duration, short",
    [
        ("PT45S", True),
        ("PT2M59S", True),
        ("PT3M", False),
        ("PT3M1S", False),
        ("PT12M", False),
        ("PT1H", False),
        ("PT1H2M", False),
        ("P1DT2M", False),
        ("P0D", False),  # live streams report P0D
        ("", False),
    ],
)
def test_is_short_video(duration, short):
    assert is_short_video(duration) is short


# --- youtube_video_search_gen -----------------------------------------------


def test_search_paginates_up_to_results_per_search(install_client):
    search = FakeResource(
        [
            search_page([f"a{i}" for i in range(50)], "page2"),
            search_page([f"b{i}" for i in range(50)], "page3"),
            search_page([f"c{i}" for i in range(20)], "page4"),
        ]
    )
    install_client(search=search)

    results = list(
        youtube_video_search_gen({"results_per_search": 120, "language": "pt"}, "lula")
    )

    assert len(results) == 120
    assert [call["maxResults"] for call in search.calls] == [50, 50, 20]
    assert [call["pageToken"] for call in search.calls] == [None, "page2", "page3"]
    assert {call["q"] for call in search.calls} == {"lula"}
    assert {call["relevanceLanguage"] for call in search.calls} == {"pt"}


def test_search_stops_when_youtube_runs_out_of_results(install_client):
    search = FakeResource([search_page(["v1", "v2", "v3"])])
    install_client(search=search)

    results = list(youtube_video_search_gen({"results_per_search": 200}, "q"))

    assert ids_of(results) == ["v1", "v2", "v3"]
    assert len(search.calls) == 1


def test_search_yields_flat_records(install_client):
    install_client(search=FakeResource([search_page(["v1"])]))

    [record] = youtube_video_search_gen({"results_per_search": 1}, "q")

    assert record == {
        "video_id": "v1",
        "video_title": "title v1",
        "video_description": "snippet description",
        "published_at": "2026-01-01T00:00:00Z",
        "channel_title": "Canal",
        "channel_id": "c1",
    }


def test_search_raises_on_quota_exhaustion(install_client):
    install_client(search=FakeResource([make_http_error(403, "quotaExceeded")]))

    with pytest.raises(QuotaExceededError):
        list(youtube_video_search_gen({"results_per_search": 50}, "q"))


# --- get_batched_video_details ----------------------------------------------


def test_batched_details_maps_only_the_ids_youtube_returned(install_client):
    videos_resource = FakeResource(
        [
            {
                "items": [
                    {
                        "id": "v1",
                        "snippet": {"description": "full one"},
                        "contentDetails": {"duration": "PT12M"},
                    },
                    {"id": "v2", "snippet": {}, "contentDetails": {"duration": "PT45S"}},
                ]
            }
        ]
    )
    install_client(videos=videos_resource)

    result = get_batched_video_details(["v1", "v2", "gone"])

    assert videos_resource.calls[0]["id"] == "v1,v2,gone"
    assert result == {
        "v1": {"full_description": "full one", "duration": "PT12M"},
        "v2": {"full_description": "", "duration": "PT45S"},
    }


# --- process_and_filter_batch -----------------------------------------------


@pytest.mark.parametrize(
    "config, kept",
    [
        ({"remove_short_videos": True}, ["long"]),
        ({"remove_short_videos": False}, ["long", "short", "tagged"]),
        ({}, ["long", "short", "tagged"]),
    ],
    ids=["shorts removed", "shorts kept", "key absent behaves as False"],
)
def test_batch_honours_remove_short_videos_from_the_passed_config(
    details, config, kept
):
    batch = [video("short"), video("long"), video("tagged")]

    assert ids_of(process_and_filter_batch(batch, config)) == kept


def test_batch_skips_videos_youtube_no_longer_serves(details):
    # Finding #1: a video deleted between search.list and videos.list
    # must be skipped, not crash the stage.
    batch = [video("gone"), video("long")]

    assert ids_of(process_and_filter_batch(batch, {})) == ["long"]


def test_batch_skips_titles_that_clean_to_nothing(details):
    assert list(process_and_filter_batch([video("long", title="😀😀")], {})) == []


def test_batch_enriches_and_cleans_each_video(details):
    [record] = process_and_filter_batch(
        [video("long", title="Lula &amp; Bolsonaro")], {}
    )

    assert record == {
        "video_id": "long",
        "video_title": "Lula &amp; Bolsonaro",  # raw title stays as the API sent it
        "channel_id": "c1",
        "video_description": "a proper description",
        "video_duration": "PT12M",
        "clean_title": "Lula & Bolsonaro",
        "clean_description": "a proper description",
    }


def test_batch_empty_description_cleans_to_none(details):
    [record] = process_and_filter_batch([video("no_desc")], {})

    assert record["clean_description"] is None


# --- filter_videos ----------------------------------------------------------


def test_filter_drops_seen_and_repeated_ids_and_records_new_ones(details):
    seen = {"short"}
    stream = iter([video("short"), video("long"), video("long"), video("tagged")])

    results = list(filter_videos(stream, seen, {}))

    assert ids_of(results) == ["long", "tagged"]
    assert seen == {"short", "long", "tagged"}


def test_filter_looks_up_details_in_batches_of_50(monkeypatch):
    batch_sizes = []

    def fake_details(ids):
        batch_sizes.append(len(ids))
        return {i: DETAILS["long"] for i in ids}

    monkeypatch.setattr(videos, "get_batched_video_details", fake_details)
    stream = iter(video(f"v{i}") for i in range(120))

    results = list(filter_videos(stream, set(), {}))

    assert len(results) == 120
    assert batch_sizes == [50, 50, 20]


@pytest.mark.parametrize(
    "config, kept",
    [({"remove_short_videos": True}, ["long"]), ({}, ["long", "short"])],
    ids=["shorts removed", "shorts kept"],
)
def test_filter_passes_its_config_down_to_the_batch(details, config, kept):
    stream = iter([video("short"), video("long")])

    assert ids_of(filter_videos(stream, set(), config)) == kept
