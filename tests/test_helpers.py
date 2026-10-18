import pytest

from src.utils.helpers import (
    clean_youtube_string,
    load_jsonl_stream,
    save_jsonl_from_generator,
)


# Finding #2: entities must be decoded *before* emoji and tags are stripped,
# or an encoded emoji/tag survives the function whose job is to remove it.
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Tom &amp; Jerry", "Tom & Jerry"),
        ("Segundo turno: &#39;Lula&#39;", "Segundo turno: 'Lula'"),
        ("Caiado: &quot;quem&quot;", 'Caiado: "quem"'),
        ("a &lt;b&gt;bold&lt;/b&gt; c", "a bold c"),
        ("texto &#128512; aqui", "texto aqui"),
        ("texto 😀 aqui", "texto aqui"),
        ("a <b>bold</b> c", "a bold c"),
        ("Lula 13 vamos", "Lula 13 vamos"),
        ("veja http://x.com/a agora", "veja agora"),
        ("veja em 12:34 agora", "veja em agora"),
        ("loooool haha", "lool haha"),
        ("Eleições 2026 — debate", "Eleições 2026 — debate"),
    ],
    ids=[
        "named entity",
        "numeric entity",
        "quot entity",
        "escaped tag stripped",
        "escaped emoji stripped",
        "real emoji stripped",
        "real tag stripped",
        "plain text untouched",
        "url removed",
        "timestamp removed",
        "repeats squashed",
        "accents and dashes kept",
    ],
)
def test_clean_youtube_string(raw, expected):
    assert clean_youtube_string(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", None, "   ", "😀😀", "&#128512;", "https://x.com"],
    ids=["empty", "None", "whitespace", "emoji only", "encoded emoji only", "url only"],
)
def test_clean_youtube_string_returns_none_when_nothing_survives(raw):
    assert clean_youtube_string(raw) is None


def test_save_jsonl_appends_and_keeps_unicode_readable(tmp_path):
    path = tmp_path / "out.jsonl"

    save_jsonl_from_generator(iter([{"q": "eleições"}]), path)
    save_jsonl_from_generator(iter([{"q": "segundo turno"}]), path)

    text = path.read_text(encoding="utf-8")
    assert text.splitlines() == ['{"q": "eleições"}', '{"q": "segundo turno"}']


def test_load_jsonl_stream_skips_blank_lines(tmp_path):
    path = tmp_path / "in.jsonl"
    path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")

    assert list(load_jsonl_stream(path)) == [{"a": 1}, {"a": 2}]


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "round.jsonl"
    rows = [{"video_id": "v1", "clean_title": "Lula & Bolsonaro"}, {"video_id": "v2"}]

    save_jsonl_from_generator(iter(rows), path)

    assert list(load_jsonl_stream(path)) == rows
