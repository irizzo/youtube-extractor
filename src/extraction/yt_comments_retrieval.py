import googleapiclient.errors

from src.utils.api import execute_request, get_youtube_client
from src.utils.helpers import clean_youtube_string
from src.utils.logger import get_extraction_logger

logger = get_extraction_logger()

DEFAULT_MAX_COMMENTS_PER_VIDEO = 50000


def get_video_comments_gen(video_id, channel_id, search_config):
    """Yields raw comments for a single video, handling pagination."""
    next_page_token = None
    comments_fetched_count = 0
    max_limit = search_config.get(
        "max_comments_per_video", DEFAULT_MAX_COMMENTS_PER_VIDEO
    )

    while comments_fetched_count < max_limit:
        try:
            request = get_youtube_client().commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
            )
            response = execute_request(request, f"commentThreads.list for {video_id}")
        except googleapiclient.errors.HttpError as e:
            # Per-video failures (comments disabled, video removed) skip the
            # video. Quota exhaustion is a QuotaExceededError, so it passes
            # through this handler and stops the run instead.
            logger.error(f"  [!] Could not fetch comments for {video_id}: {e.reason}")
            break

        items = response.get("items", [])
        if not items:
            break

        for item in items:
            snippet = item["snippet"]["topLevelComment"]["snippet"]

            author_channel = snippet.get("authorChannelId", {})
            if author_channel.get("value") == channel_id:
                continue

            yield {
                "video_id": video_id,
                "comment_id": item["id"],
                "raw_text": snippet.get("textOriginal", ""),
                "comment_likes": snippet.get("likeCount", 0),
                "comment_replies": item["snippet"].get("totalReplyCount", 0),
            }
            comments_fetched_count += 1

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    logger.info(
        f"  Collected {comments_fetched_count} comments for video_id: {video_id}"
    )


def filter_comments(comments_generator):
    """Applies NLP preprocessing and yields only valid, non-empty comments."""
    for comment in comments_generator:
        raw_text = comment["raw_text"]

        cleaned_text = clean_youtube_string(raw_text)
        if not cleaned_text:
            continue

        comment["clean_text"] = cleaned_text

        yield comment
