from dotenv import load_dotenv
import os

load_dotenv()

""" 
    Go to https://developers.google.com/youtube/v3/docs/search/list?hl=pt-br to see the search.list() method native parameters
"""
# optional
dir_config = {
    "current_results_dir": "data",
    "videos_output_filename": "videos.jsonl",
    "videos_checkpoint_filename": "videos_checkpoint.json",
    "comments_output_filename": "comments.jsonl",
    "comments_checkpoint_filename": "comments_checkpoint.json",
}

youtube_search_config = {
    "youtube_api_key": os.getenv("YT_API_KEY"),  # required
    "queries": [
        "(eleições|bolsonaro|lula|'segundo turno')",
    ],
    "remove_short_videos": False,
    "language": "pt",
    "published_after": "2026-01-01T00:00:00Z",
    "results_per_search": 50,
    "max_comments_per_video": 100,
}
