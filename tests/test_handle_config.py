import os

import pytest

from src.utils.handle_config import (
    RUN_TIMESTAMP,
    handle_dir_config,
    handle_search_config,
)


def test_search_config_applies_defaults():
    config = handle_search_config({"youtube_api_key": "k"})

    assert config == {
        "youtube_api_key": "k",
        "results_per_search": 50,
        "language": "en",
        "remove_short_videos": False,
        "max_comments_per_video": 50000,
        "queries": [""],
    }


def test_search_config_user_values_win_and_extras_are_kept():
    user = {
        "youtube_api_key": "k",
        "results_per_search": 5,
        "remove_short_videos": True,
        "published_after": "2026-01-01T00:00:00Z",
    }

    config = handle_search_config(user)

    assert config["results_per_search"] == 5
    assert config["remove_short_videos"] is True
    assert config["published_after"] == "2026-01-01T00:00:00Z"


def test_search_config_does_not_mutate_the_callers_dict():
    user = {"youtube_api_key": "k"}

    handle_search_config(user)

    assert user == {"youtube_api_key": "k"}


@pytest.mark.parametrize(
    "user",
    [{}, {"youtube_api_key": None}, {"youtube_api_key": ""}],
    ids=["missing", "None (env var unset)", "empty"],
)
def test_search_config_rejects_a_missing_api_key(user):
    with pytest.raises(ValueError, match="API Key"):
        handle_search_config(user)


def test_dir_config_builds_every_path_and_creates_the_dir(tmp_path):
    run_dir = tmp_path / "extraction" / "run1"

    paths = handle_dir_config({"current_results_dir": str(run_dir)})

    assert run_dir.is_dir()
    assert paths == {
        "CURRENT_DIR": str(run_dir),
        "VIDEOS_OUTPUT_FILE": os.path.join(run_dir, "videos.jsonl"),
        "VIDEOS_CHECKPOINT_FILE": os.path.join(run_dir, "videos_checkpoint.json"),
        "COMMENTS_OUTPUT_FILE": os.path.join(run_dir, "comments.jsonl"),
        "COMMENTS_CHECKPOINT_FILE": os.path.join(run_dir, "comments_checkpoint.json"),
        "LOG_FILE": os.path.join(run_dir, f"extraction_{RUN_TIMESTAMP}.log"),
    }


def test_dir_config_honours_custom_filenames(tmp_path):
    paths = handle_dir_config(
        {"current_results_dir": str(tmp_path), "videos_output_filename": "v.jsonl"}
    )

    assert paths["VIDEOS_OUTPUT_FILE"] == os.path.join(tmp_path, "v.jsonl")


def test_dir_config_log_name_is_fixed_for_the_whole_run(tmp_path):
    # RUN_TIMESTAMP is evaluated once at import, so every caller agrees.
    first = handle_dir_config({"current_results_dir": str(tmp_path)})
    second = handle_dir_config({"current_results_dir": str(tmp_path)})

    assert first["LOG_FILE"] == second["LOG_FILE"]
