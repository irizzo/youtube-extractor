import os
from datetime import datetime

RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def handle_search_config(user_config):
    default_config = {
        "results_per_search": 50,
        "language": "en",
        "remove_short_videos": False,
        "max_comments_per_video": 50000,
        "queries": [""],
    }

    final_config = {**default_config, **user_config}

    if not final_config.get("youtube_api_key"):
        raise ValueError(
            "[ERROR] YouTube API Key not found. Please check your .env file."
        )

    return final_config


def handle_dir_config(dir_config):
    default_config = {
        "current_results_dir": "data",
        "videos_output_filename": "videos.jsonl",
        "videos_checkpoint_filename": "videos_checkpoint.json",
        "comments_output_filename": "comments.jsonl",
        "comments_checkpoint_filename": "comments_checkpoint.json",
    }

    config = {**default_config, **dir_config}

    CURRENT_DIR = config["current_results_dir"]
    os.makedirs(CURRENT_DIR, exist_ok=True)

    VIDEOS_OUTPUT_FILE = os.path.join(CURRENT_DIR, config["videos_output_filename"])
    VIDEOS_CHECKPOINT_FILE = os.path.join(
        CURRENT_DIR, config["videos_checkpoint_filename"]
    )
    COMMENTS_OUTPUT_FILE = os.path.join(CURRENT_DIR, config["comments_output_filename"])
    COMMENTS_CHECKPOINT_FILE = os.path.join(
        CURRENT_DIR, config["comments_checkpoint_filename"]
    )
    LOG_FILE = os.path.join(CURRENT_DIR, f"extraction_{RUN_TIMESTAMP}.log")

    return {
        "CURRENT_DIR": CURRENT_DIR,
        "VIDEOS_OUTPUT_FILE": VIDEOS_OUTPUT_FILE,
        "VIDEOS_CHECKPOINT_FILE": VIDEOS_CHECKPOINT_FILE,
        "COMMENTS_OUTPUT_FILE": COMMENTS_OUTPUT_FILE,
        "COMMENTS_CHECKPOINT_FILE": COMMENTS_CHECKPOINT_FILE,
        "LOG_FILE": LOG_FILE,
    }
