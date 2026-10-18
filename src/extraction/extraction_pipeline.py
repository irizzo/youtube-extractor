import json
import os

from googleapiclient.errors import HttpError

from .yt_videos_retrieval import youtube_video_search_gen, filter_videos
from .yt_comments_retrieval import get_video_comments_gen, filter_comments

from src.utils.api import QuotaExceededError
from src.utils.helpers import save_jsonl_from_generator
from src.utils.logger import get_extraction_logger

logger = get_extraction_logger()


def run_videos_extraction_pipeline(search_config, output_file_path, checkpoint_file):
    """Main orchestrator with query-level checkpointing.

    Returns True if every query finished, False if the stage stopped early
    (quota exhausted or an unrecoverable API error). An interrupted query is
    never checkpointed, so a later run picks it up again.
    """

    # seed global state from existing dataset to prevent duplicates across runs
    global_seen_video_ids = set()
    if os.path.exists(output_file_path):
        with open(output_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        global_seen_video_ids.add(record["video_id"])
                    except json.JSONDecodeError:
                        continue

    logger.info(
        f"Loaded {len(global_seen_video_ids)} previously saved video IDs to prevent duplicates."
    )

    # load completed queries from checkpoint
    completed_queries = []
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            completed_queries = json.load(f)

    logger.info(
        f"Resuming pipeline. {len(completed_queries)} queries already processed."
    )

    for query in search_config["queries"]:
        if query in completed_queries:
            logger.info(f"Skipping '{query}' (Already processed).")
            continue

        logger.info(f"--- Starting extraction for: '{query}' ---")

        try:
            raw_stream = youtube_video_search_gen(search_config, query)
            filtered_stream = filter_videos(
                raw_stream, global_seen_video_ids, search_config
            )

            save_jsonl_from_generator(filtered_stream, output_file_path)
        except QuotaExceededError as error:
            logger.error(
                f"{error} Videos found so far were saved, but '{query}' was NOT "
                "checkpointed. Re-run after the quota resets to finish it."
            )
            return False
        except HttpError as error:
            logger.error(
                f"Aborting '{query}' after an API error: {error}. The query was "
                "NOT checkpointed, so a later run will retry it."
            )
            return False

        completed_queries.append(query)
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(completed_queries, f, ensure_ascii=False)

        logger.info(f"--- Finished and checkpointed: '{query}' ---")

    return True


def run_comments_pipeline(
    videos_list, output_file_path, checkpoint_file, search_config
):
    """
    Extracts, filters, and saves comments for a list of video dictionaries.
    Checkpoints progress by video_id to safely resume after interruptions.

    Returns True if every video was processed, False if the stage stopped
    early because the quota ran out.
    """

    # Load completed video_ids from checkpoint
    completed_videos = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            completed_videos = set(json.load(f))

    logger.info(
        f"Resuming comments pipeline. {len(completed_videos)} videos already processed."
    )

    for video in videos_list:
        video_id = video["video_id"]
        channel_id = video["channel_id"]

        if video_id in completed_videos:
            logger.info(f"Skipping video '{video_id}' (Already processed).")
            continue

        logger.info(f"--- Extracting comments for video: {video_id} ---")

        try:
            raw_comments_stream = get_video_comments_gen(
                video_id, channel_id, search_config
            )
            filtered_comments_stream = filter_comments(raw_comments_stream)

            save_jsonl_from_generator(filtered_comments_stream, output_file_path)
        except QuotaExceededError as error:
            logger.error(
                f"{error} Video '{video_id}' was NOT checkpointed. Any comments "
                "already written for it will be fetched again on the next run, "
                "so deduplicate by comment_id if that happens."
            )
            return False

        completed_videos.add(video_id)
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(list(completed_videos), f, ensure_ascii=False)

        logger.info(f"--- Finished and checkpointed video: {video_id} ---")

    return True
