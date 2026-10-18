import json
import html, emoji, re


def save_jsonl_from_generator(generator, output_file_path):
    with open(output_file_path, "a", encoding="utf-8") as f:
        for result in generator:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")


def load_jsonl_stream(file_path):
    """Yields one flat video dictionary at a time from a JSONL file."""
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def clean_youtube_string(text):
    """
    Preprocess youtube comments, video titles or descriptions.
    """

    if not text:
        return None

    text = text.strip().encode("utf-8", "ignore").decode("utf-8")

    # unescape first, so entity-encoded emoji and tags (&#128512;, &lt;b&gt;)
    # become real characters that the steps below can actually strip
    text = html.unescape(text)  # unescape html entities as &amp; &lt; &gt; etc
    text = emoji.replace_emoji(text, replace="")

    if not text:
        return None

    text = re.sub(r"<[^>]+>", " ", text)  # remove html codes
    text = re.sub(
        r"(?:at\s+)?\[?\b\d{1,2}:\d{2}(?::\d{2})?[a-zA-Z]*\]?",
        "",
        text,
        flags=re.IGNORECASE,
    )  # remove timestamps and related at, am/pm, [] etc
    text = re.sub(
        r"http\S+|www\S+|https\S+", "", text, flags=re.MULTILINE
    )  # remove urls
    text = re.sub(r"[→➡►]", "", text)  # remove arrow chars
    text = re.sub(r"([a-zA-Z])\1{2,}", r"\1\1", text)  # squash overly repeated letters
    text = re.sub(r"\.{4,}", "...", text)  # squash overly repeated punctuation
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None

    return text
