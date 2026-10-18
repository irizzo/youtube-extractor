import pytest

from src.extraction.yt_comments_retrieval import filter_comments, get_video_comments_gen
from src.utils.api import QuotaExceededError

from fakes import FakeResource, make_http_error


def thread(comment_id, text="um comentário", author="viewer", likes=0, replies=0):
    snippet = {"textOriginal": text, "likeCount": likes}
    if author is not None:
        snippet["authorChannelId"] = {"value": author}
    return {
        "id": comment_id,
        "snippet": {"topLevelComment": {"snippet": snippet}, "totalReplyCount": replies},
    }


def page(threads, next_token=None):
    response = {"items": threads}
    if next_token:
        response["nextPageToken"] = next_token
    return response


def full_page(prefix, next_token=None):
    return page([thread(f"{prefix}-{i}") for i in range(100)], next_token)


def test_yields_flat_records_and_skips_the_channel_owner(install_client):
    install_client(
        comment_threads=FakeResource(
            [
                page(
                    [
                        thread("c1", text="ótimo vídeo", likes=3, replies=2),
                        thread("c2", author="owner"),
                        thread("c3", author=None),  # no authorChannelId at all
                    ]
                )
            ]
        )
    )

    results = list(get_video_comments_gen("v1", "owner", {}))

    assert results == [
        {
            "video_id": "v1",
            "comment_id": "c1",
            "raw_text": "ótimo vídeo",
            "comment_likes": 3,
            "comment_replies": 2,
        },
        {
            "video_id": "v1",
            "comment_id": "c3",
            "raw_text": "um comentário",
            "comment_likes": 0,
            "comment_replies": 0,
        },
    ]


def test_follows_next_page_tokens(install_client):
    threads = FakeResource([full_page("a", "t2"), page([thread("b-0")])])
    install_client(comment_threads=threads)

    results = list(get_video_comments_gen("v1", "owner", {}))

    assert len(results) == 101
    assert [call["pageToken"] for call in threads.calls] == [None, "t2"]
    assert {call["videoId"] for call in threads.calls} == {"v1"}
    assert {call["maxResults"] for call in threads.calls} == {100}


def test_max_comments_per_video_is_checked_between_pages(install_client):
    # The cap is enforced per page, so the real ceiling is the next multiple
    # of 100 above it: 150 fetches two full pages and stops.
    threads = FakeResource(
        [full_page("a", "t2"), full_page("b", "t3"), full_page("c", "t4")]
    )
    install_client(comment_threads=threads)

    results = list(get_video_comments_gen("v1", "owner", {"max_comments_per_video": 150}))

    assert len(results) == 200
    assert len(threads.calls) == 2


def test_per_video_api_errors_skip_the_video(install_client):
    install_client(comment_threads=FakeResource([make_http_error(403, "commentsDisabled")]))

    assert list(get_video_comments_gen("v1", "owner", {})) == []


def test_api_error_mid_video_keeps_the_pages_already_fetched(install_client):
    install_client(
        comment_threads=FakeResource(
            [page([thread("c1")], "t2"), make_http_error(404, "videoNotFound")]
        )
    )

    assert [c["comment_id"] for c in get_video_comments_gen("v1", "owner", {})] == ["c1"]


def test_quota_exhaustion_is_not_swallowed_as_a_per_video_error(install_client):
    install_client(comment_threads=FakeResource([make_http_error(403, "quotaExceeded")]))

    with pytest.raises(QuotaExceededError):
        list(get_video_comments_gen("v1", "owner", {}))


def test_filter_comments_adds_clean_text_and_drops_empty_ones():
    comments = [
        {"comment_id": "c1", "raw_text": "Muito bom &amp; claro 😀"},
        {"comment_id": "c2", "raw_text": "😀😀😀"},
        {"comment_id": "c3", "raw_text": ""},
    ]

    results = list(filter_comments(iter(comments)))

    assert results == [
        {
            "comment_id": "c1",
            "raw_text": "Muito bom &amp; claro 😀",
            "clean_text": "Muito bom & claro",
        }
    ]
