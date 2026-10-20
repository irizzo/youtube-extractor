import re

from src.utils.api import execute_request, get_youtube_client
from src.utils.helpers import clean_youtube_string
from src.utils.logger import get_extraction_logger

logger = get_extraction_logger()


def youtube_video_search_gen(config, query):
    """Yields raw video snippets, handling YouTube's max 50 results per page limit."""
    total_needed = config.get("results_per_search", 50)
    total_fetched = 0
    next_page_token = None

    while total_fetched < total_needed:
        max_results = min(50, total_needed - total_fetched)

        logger.info(
            f"[{query}] Fetching batch... (Total fetched so far: {total_fetched})"
        )

        request = (
            get_youtube_client()
            .search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                publishedAfter=config.get("published_after"),
                relevanceLanguage=config.get("language"),
                pageToken=next_page_token,
            )
        )
        response = execute_request(request, f"search.list for '{query}'")
        items = response.get("items", [])

        for item in items:
            yield {
                "video_id": item["id"]["videoId"],
                "video_title": item["snippet"]["title"],
                "video_description": item["snippet"]["description"],
                "published_at": item["snippet"]["publishedAt"],
                "channel_title": item["snippet"]["channelTitle"],
                "channel_id": item["snippet"]["channelId"],
            }

        total_fetched += len(items)
        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break


def is_short_video(video_duration):
    """Parses ISO 8601 duration to determine if video is < 3 minutes (as 3 minutes is the maximum duration for the shorts form, based on the youtube rules)"""

    # ISO 8601: P[n]DT[n]H[n]M[n]S
    pattern = re.compile(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    match = pattern.match(video_duration)

    if not match:
        return False

    days, hours, minutes, seconds = match.groups()

    if days or hours:
        return False

    minutes = int(minutes) if minutes else 0
    return minutes < 3


def get_batched_video_details(video_ids):
    """Fetches durations and descriptions for up to 50 videos in a single API call."""

    request = (
        get_youtube_client()
        .videos()
        .list(part="snippet,contentDetails", id=",".join(video_ids))
    )
    response = execute_request(request, f"videos.list for {len(video_ids)} video(s)")

    details = {}
    for item in response.get("items", []):
        details[item["id"]] = {
            "full_description": item["snippet"].get("description", ""),
            "duration": item.get("contentDetails", {}).get("duration", ""),
        }
    return details


def filter_videos(videos_generator, global_seen_video_ids, search_config):
    """Filters duplicates and shorts, batching API calls for efficiency."""
    batch = []

    for video in videos_generator:
        video_id = video["video_id"]

        if video_id in global_seen_video_ids:
            continue

        global_seen_video_ids.add(video_id)
        batch.append(video)

        if len(batch) == 50:
            yield from process_and_filter_batch(batch, search_config)
            batch = []

    if batch:
        yield from process_and_filter_batch(batch, search_config)


def process_and_filter_batch(batch, search_config):
    """Helper to apply filtering logic to a specific batch of videos."""

    video_ids = [v["video_id"] for v in batch]
    details_map = get_batched_video_details(video_ids)
    remove_shorts = search_config.get("remove_short_videos")

    for video in batch:
        video_id = video["video_id"]

        logger.info(f"Processing video [{video_id}] {video["video_title"]}")

        details = details_map.get(video_id)

        if not details:
            continue

        if remove_shorts:
            if (
                is_short_video(details["duration"])
                or "#short" in details["full_description"].lower()
            ):
                continue

        clean_title = clean_youtube_string(video["video_title"])
        clean_desc = (
            clean_youtube_string(details["full_description"])
            if details["full_description"]
            else None
        )

        if not clean_title:
            continue

        video.update(
            {
                "video_description": details["full_description"],
                "video_duration": details["duration"],
                "clean_title": clean_title,
                "clean_description": clean_desc,
            },
        )

        yield video
