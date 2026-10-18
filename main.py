from src.config import youtube_search_config, dir_config
from src.utils.api import init_youtube_client
from src.utils.handle_config import handle_search_config, handle_dir_config
from src.utils.helpers import load_jsonl_stream
from src.utils.logger import configure_extraction_logger

from src.extraction.extraction_pipeline import run_videos_extraction_pipeline
from src.extraction.extraction_pipeline import run_comments_pipeline


def main():
    # Composition root: resolve config, build the API client, then hand both
    # to the steps. Nothing below this function reads config or credentials.
    search_config = handle_search_config(youtube_search_config)
    output_config = handle_dir_config(dir_config)

    configure_extraction_logger(output_config["LOG_FILE"])
    init_youtube_client(search_config)

    videos_completed = run_videos_extraction_pipeline(
        search_config=search_config,
        output_file_path=output_config["VIDEOS_OUTPUT_FILE"],
        checkpoint_file=output_config["VIDEOS_CHECKPOINT_FILE"],
    )

    if not videos_completed:
        # Out of quota or a hard API failure. Running the comments stage now
        # would fail on every video, so stop and let the next run resume.
        return

    video_generator = load_jsonl_stream(output_config["VIDEOS_OUTPUT_FILE"])
    run_comments_pipeline(
        videos_list=video_generator,
        output_file_path=output_config["COMMENTS_OUTPUT_FILE"],
        checkpoint_file=output_config["COMMENTS_CHECKPOINT_FILE"],
        search_config=search_config,
    )


if __name__ == "__main__":
    main()
