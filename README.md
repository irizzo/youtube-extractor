# YouTube Video Metadata & Comments Extractor

A configurable pipeline that collects **videos** and their **comments** from the YouTube Data API v3 and stores them as JSONL datasets, ready for text analysis.

A run has two stages:

1. **Videos** — runs one YouTube search per query, enriches each hit with its full description and duration, discards duplicates (and optionally Shorts), and writes `videos.jsonl`.
2. **Comments** — streams `videos.jsonl` back in, fetches the top-level comments of every video, cleans the text, and writes `comments.jsonl`.

Both stages are **checkpointed**: if a run stops halfway (quota exhausted, network error, `Ctrl+C`), running it again resumes where it stopped instead of re-downloading what you already have.

## Set Up

1. **Install uv**

Follow the steps to install [uv](https://docs.astral.sh/uv/) (python environment manager).

2. **Sync the dependencies**

At the root of the project, run:

```bash
uv sync
```

3. **Get your YouTube Data API API KEY**

Go to the Google Developer's Console and follow the steps to create a project and get your **API KEY**. Than create an `.env` file in the root of the project, and add your API KEY under the `YT_API_KEY` var, as in the `.env.example` example file.

## Running

### Config

You can set the YouTube search configuration by changing the following parameters. Other native search parameters can be found at [`search.list()`](https://developers.google.com/youtube/v3/docs/search/list) method's documentation page, but are **not yet implemented**.

#### `youtube_search_config` — what to collect

| Parameter | Required | Default | Description |
| --- | --- | --- | --- |
| `youtube_api_key` | yes | — | Read from `YT_API_KEY` in your `.env`. The run fails immediately if it is missing. |
| `queries` | no | `[""]` | List of search strings. **One search is run per entry**, and the results of all of them land in the same output file. |
| `remove_short_videos` | no | `False` | `True` discards videos shorter than 3 minutes or with `#short` in the description. |
| `language` | no | `"en"` | ISO 639-1 code sent as `relevanceLanguage`. It *biases* results toward that language, it does not hard-filter them. |
| `published_after` | no | — | RFC 3339 timestamp (`"2026-01-01T00:00:00Z"`). Only videos published after this moment are returned. |
| `results_per_search` | no | `50` | Videos requested **per query**, fetched in pages of 50. YouTube stops paginating a single search at roughly 500 results, so the stage ends early when the API returns no next page. |
| `max_comments_per_video` | no | `50000` | Upper bound on comments collected per video. Checked between pages of 100, so the effective ceiling is the next multiple of 100. |

Queries accept YouTube's search operators: `|` means OR, an space ` ` means AND, quotes match an exact phrase, and `-` excludes a term. The shipped example

```python
"(eleições|bolsonaro|lula|'segundo turno') (brasil)"
```

matches videos mentioning any of those four terms AND "brasil".

#### `dir_config` — where to write it

| Parameter | Default | Description |
| --- | --- | --- |
| `current_results_dir` | `"data"` | Directory for the outputs and checkpoints. Created if it does not exist. |
| `videos_output_filename` | `"videos.jsonl"` | Collected videos. |
| `videos_checkpoint_filename` | `"videos_checkpoint.json"` | Queries already finished. |
| `comments_output_filename` | `"comments.jsonl"` | Collected comments. |
| `comments_checkpoint_filename` | `"comments_checkpoint.json"` | Videos whose comments are already collected. |

Since every file is **appended** to, **give each collection its own `current_results_dir`** (for example `data/extraction/20261015_111836`) when you want a separate dataset rather than a continuation of the previous one.

### Run

From the root of the project:

```bash
uv run main.py
```

Progress is printed to the terminal and written to a log file inside `current_results_dir`, named after the moment the run started — `extraction_20261018_114459.log` (a rotating 5 MB log, two backups kept). Each execution gets its own file, so previous runs' logs are never overwritten.

## Output

```
data/
├── videos.jsonl                      # one video per line
├── videos_checkpoint.json            # ["query already done", ...]
├── comments.jsonl                    # one comment per line
├── comments_checkpoint.json          # ["video_id already done", ...]
└── extraction_20261018_114459.log    # one log per execution
```

### `videos.jsonl`

| Field | Description |
| --- | --- |
| `video_id` | YouTube video ID. |
| `video_title` | Original title. |
| `video_description` | Full description, as returned by the API. |
| `published_at` | Publication timestamp (RFC 3339). |
| `channel_title` | Channel display name. |
| `channel_id` | Channel ID, used to drop the channel's own comments later. |
| `video_duration` | ISO 8601 duration, e.g. `PT5M1S`. |
| `clean_title` | Preprocessed title (`null` if nothing survived cleaning). |
| `clean_description` | Preprocessed description (`null` if empty or nothing survived cleaning). |

### `comments.jsonl`

| Field | Description |
| --- | --- |
| `video_id` | Video the comment belongs to. |
| `comment_id` | YouTube comment ID. |
| `raw_text` | Original comment text. |
| `comment_likes` | Like count at collection time. |
| `comment_replies` | Number of replies (the replies themselves are not collected). |
| `clean_text` | Preprocessed text. |

### What gets filtered out

- Videos already present in `videos.jsonl`, so repeated terms across queries never duplicate a row.
- Videos under 3 minutes or tagged `#short`, when `remove_short_videos` is `True`.
- Comments written by the video's own channel.
- Comments that are empty after cleaning.
- Replies — only top-level comments are collected, capped at `max_comments_per_video`.

Videos with comments disabled, or otherwise unreachable, are logged and skipped; the run continues.

### Text cleaning

The `clean_*` fields first have HTML entities decoded (`&amp;` → `&`, `&#39;` → `'`), then emojis, HTML tags, URLs, timestamps (`12:34`), and arrow characters removed, overly repeated letters and punctuation squashed (`loooool` → `lool`), and whitespace collapsed.

The original text is always kept alongside and is never modified — `video_title` and `raw_text` stay exactly as the API returned them, escaped entities included. Search results arrive HTML-escaped, so expect `&#39;` in `video_title` even though `clean_title` reads `'`. That means you can always re-clean from the stored raw text without collecting again.

## Resuming and starting over

Output files are appended to and checkpoints are written after each query (videos) and after each video (comments), so an interrupted run is safe to repeat.

- **Add a new query** — append it to `queries` and run again. Queries listed in `videos_checkpoint.json` are skipped, so only the new one costs quota.
- **Start a clean dataset** — point `current_results_dir` at a new directory, or delete the four files in the current one.
- **Careful when deleting only a checkpoint** — removing `videos_checkpoint.json` re-runs the searches but the duplicate check still protects `videos.jsonl`. Removing `comments_checkpoint.json` has no such protection: every comment is fetched and appended a second time.

The whole `data/` directory is gitignored, so collected datasets never enter the repository. Back them up deliberately — nothing in git protects them.

## API quota

The YouTube Data API gives a project 10,000 units per day by default:

| Call | Cost | Made once per |
| --- | --- | --- |
| `search.list` | 100 units | page of up to 50 videos |
| `videos.list` | 1 unit | batch of up to 50 videos (durations and full descriptions) |
| `commentThreads.list` | 1 unit | page of up to 100 comments |

The video stage is the expensive one: `results_per_search: 200` with a single query costs about 404 units, while collecting 100,000 comments costs around 1,000. When quota runs out the API returns `403 quotaExceeded` — the checkpoints let you pick the run back up the next day.

## Tests

From the root of the project:

```bash
uv run pytest
```

The suite needs **no API key and spends no quota**: the YouTube client is replaced by a fake, and every file is written to a temporary directory, never to `data/`. It covers the text cleaner, config defaults, quota-error classification, both retrieval steps (pagination, Shorts filtering, per-video caps), and checkpoint/resume behaviour of both stages.

## Project structure

```
main.py                              # entry point: videos stage, then comments stage
src/
├── config.py                        # all user-facing settings
├── extraction/
│   ├── extraction_pipeline.py       # orchestration, checkpointing, deduplication
│   ├── yt_videos_retrieval.py       # search.list + videos.list, Shorts filter
│   └── yt_comments_retrieval.py     # commentThreads.list, comment filter
└── utils/
    ├── api.py                       # shared API client, quota-aware request execution
    ├── handle_config.py             # applies defaults, validates the API key, builds paths
    ├── helpers.py                   # JSONL streaming and text preprocessing
    └── logger.py                    # console + rotating file logger
tests/
├── fakes.py                         # fake YouTube client, HttpError builder
├── conftest.py                      # fixtures: fake-client install, logger cleanup
└── test_*.py                        # one file per module, plus test_isolation.py
```
