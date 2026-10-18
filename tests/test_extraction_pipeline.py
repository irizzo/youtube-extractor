"""Checkpoint and resume behaviour of both stages, with the API stubbed out."""

import json

import pytest

from src.extraction import extraction_pipeline as pipeline
from src.extraction import yt_videos_retrieval as videos
from src.utils.api import QuotaExceededError

from fakes import make_http_error


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def videos_files(tmp_path):
    return tmp_path / "videos.jsonl", tmp_path / "videos_checkpoint.json"


@pytest.fixture
def comments_files(tmp_path):
    return tmp_path / "comments.jsonl", tmp_path / "comments_checkpoint.json"


@pytest.fixture
def searched(monkeypatch):
    """Replaces search.list with one video per query; records the queries run."""
    queries = []

    def fake_search(config, query):
        queries.append(query)
        yield {"video_id": f"v-{query}", "channel_id": "c1", "video_title": query}

    monkeypatch.setattr(pipeline, "youtube_video_search_gen", fake_search)
    monkeypatch.setattr(pipeline, "filter_videos", lambda stream, seen, config: stream)
    return queries


@pytest.fixture
def fetched(monkeypatch):
    """Replaces commentThreads.list with two comments per video; records the
    video IDs fetched and the max_comments_per_video each call received."""
    calls = []

    def fake_comments(video_id, channel_id, search_config):
        calls.append((video_id, search_config.get("max_comments_per_video")))
        for i in range(2):
            yield {"video_id": video_id, "comment_id": f"{video_id}-{i}", "raw_text": "oi"}

    monkeypatch.setattr(pipeline, "get_video_comments_gen", fake_comments)
    monkeypatch.setattr(pipeline, "filter_comments", lambda stream: stream)
    return calls


VIDEOS = [{"video_id": "v1", "channel_id": "c1"}, {"video_id": "v2", "channel_id": "c1"}]


# --- videos stage -----------------------------------------------------------


def test_videos_clean_run_checkpoints_every_query(videos_files, searched):
    out, checkpoint = videos_files

    completed = pipeline.run_videos_extraction_pipeline(
        {"queries": ["q1", "q2"]}, out, checkpoint
    )

    assert completed is True
    assert json.loads(checkpoint.read_text()) == ["q1", "q2"]
    assert [r["video_id"] for r in read_jsonl(out)] == ["v-q1", "v-q2"]


def test_videos_resume_skips_checkpointed_queries(videos_files, searched):
    out, checkpoint = videos_files
    checkpoint.write_text('["q1"]')

    pipeline.run_videos_extraction_pipeline({"queries": ["q1", "q2"]}, out, checkpoint)

    assert searched == ["q2"]
    assert json.loads(checkpoint.read_text()) == ["q1", "q2"]


@pytest.mark.parametrize(
    "error",
    [
        QuotaExceededError("Daily YouTube API quota exhausted during search.list."),
        make_http_error(500, "backendError"),
    ],
    ids=["quota exhausted", "unrecoverable API error"],
)
def test_videos_abort_keeps_partial_results_but_not_the_checkpoint(
    videos_files, monkeypatch, error
):
    out, checkpoint = videos_files
    queries = []

    def failing_search(config, query):
        queries.append(query)
        yield {"video_id": "v1", "channel_id": "c1"}
        raise error

    monkeypatch.setattr(pipeline, "youtube_video_search_gen", failing_search)
    monkeypatch.setattr(pipeline, "filter_videos", lambda stream, seen, config: stream)

    completed = pipeline.run_videos_extraction_pipeline(
        {"queries": ["q1", "q2"]}, out, checkpoint
    )

    assert completed is False
    assert queries == ["q1"]  # the run stops; q2 is never attempted
    assert len(read_jsonl(out)) == 1
    assert not checkpoint.exists()


def test_videos_resume_never_rewrites_a_video_already_on_disk(
    videos_files, monkeypatch
):
    # The real filter_videos runs here: the pipeline seeds its seen-set from
    # the existing output, so a re-run of an unfinished query adds only new IDs.
    out, checkpoint = videos_files
    out.write_text('{"video_id": "v1", "clean_title": "from the first run"}\n')

    monkeypatch.setattr(
        pipeline,
        "youtube_video_search_gen",
        lambda config, query: iter(
            [{"video_id": i, "video_title": f"t {i}", "channel_id": "c1"} for i in ("v1", "v2")]
        ),
    )
    monkeypatch.setattr(
        videos,
        "get_batched_video_details",
        lambda ids: {i: {"full_description": "d", "duration": "PT12M"} for i in ids},
    )

    pipeline.run_videos_extraction_pipeline({"queries": ["q1"]}, out, checkpoint)

    rows = read_jsonl(out)
    assert [r["video_id"] for r in rows] == ["v1", "v2"]
    assert rows[0]["clean_title"] == "from the first run"


def test_videos_seeding_tolerates_blank_and_truncated_lines(videos_files, monkeypatch):
    out, checkpoint = videos_files
    out.write_text('{"video_id": "v1"}\n\n{"video_id": "v2"\n')
    seen_sets = []

    def capture_filter(stream, seen, config):
        seen_sets.append(set(seen))
        return stream

    monkeypatch.setattr(pipeline, "youtube_video_search_gen", lambda c, q: iter([]))
    monkeypatch.setattr(pipeline, "filter_videos", capture_filter)

    assert pipeline.run_videos_extraction_pipeline({"queries": ["q1"]}, out, checkpoint)
    assert seen_sets == [{"v1"}]


# --- comments stage ---------------------------------------------------------


def test_comments_clean_run_checkpoints_every_video(comments_files, fetched):
    out, checkpoint = comments_files

    completed = pipeline.run_comments_pipeline(VIDEOS, out, checkpoint, {})

    assert completed is True
    assert sorted(json.loads(checkpoint.read_text())) == ["v1", "v2"]
    assert len(read_jsonl(out)) == 4


def test_comments_resume_skips_checkpointed_videos(comments_files, fetched):
    out, checkpoint = comments_files
    checkpoint.write_text('["v1"]')

    pipeline.run_comments_pipeline(VIDEOS, out, checkpoint, {})

    assert [video_id for video_id, _ in fetched] == ["v2"]
    assert sorted(json.loads(checkpoint.read_text())) == ["v1", "v2"]


def test_comments_quota_mid_video_keeps_partial_comments_but_not_the_checkpoint(
    comments_files, monkeypatch
):
    out, checkpoint = comments_files
    attempted = []

    def failing_comments(video_id, channel_id, search_config):
        attempted.append(video_id)
        yield {"video_id": video_id, "comment_id": "c-1", "raw_text": "saved"}
        raise QuotaExceededError("quota exhausted")

    monkeypatch.setattr(pipeline, "get_video_comments_gen", failing_comments)
    monkeypatch.setattr(pipeline, "filter_comments", lambda stream: stream)

    completed = pipeline.run_comments_pipeline(VIDEOS, out, checkpoint, {})

    assert completed is False
    assert attempted == ["v1"]
    assert len(read_jsonl(out)) == 1
    assert not checkpoint.exists()


def test_comments_quota_before_the_first_page_is_caught_too(comments_files, monkeypatch):
    # A plain function raising at call time, not a generator raising on
    # iteration: the stream is built inside the try, so both are covered.
    out, checkpoint = comments_files

    def failing_immediately(video_id, channel_id, search_config):
        raise QuotaExceededError("quota exhausted")

    monkeypatch.setattr(pipeline, "get_video_comments_gen", failing_immediately)

    assert pipeline.run_comments_pipeline(VIDEOS, out, checkpoint, {}) is False
    assert not checkpoint.exists()


def test_comments_config_reaches_the_leaf_and_runs_do_not_share_it(
    tmp_path, fetched
):
    pipeline.run_comments_pipeline(
        VIDEOS, tmp_path / "a.jsonl", tmp_path / "a.json", {"max_comments_per_video": 7}
    )
    pipeline.run_comments_pipeline(
        VIDEOS[:1], tmp_path / "b.jsonl", tmp_path / "b.json", {"max_comments_per_video": 999}
    )

    assert fetched == [("v1", 7), ("v2", 7), ("v1", 999)]
