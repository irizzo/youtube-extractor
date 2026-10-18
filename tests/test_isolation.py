"""main.py is the only composition root: steps are inert until it wires them."""

import ast
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from src.utils.logger import configure_extraction_logger

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_importing_main_and_every_step_has_no_side_effects(tmp_path):
    # A fresh interpreter, so nothing earlier in the test session can mask a
    # side effect. Running from an empty directory shows whether anything
    # (a data/ dir, a log file) gets created.
    probe = """
import json, logging, os
import main
import src.utils.api as api
from src.extraction import extraction_pipeline, yt_comments_retrieval, yt_videos_retrieval
print(json.dumps({
    "client_built": api._youtube_client is not None,
    "log_handlers": len(logging.getLogger("extraction_logger").handlers),
    "files_created": os.listdir("."),
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=True,
    )

    # json.loads also fails if an import printed anything of its own.
    assert json.loads(result.stdout) == {
        "client_built": False,
        "log_handlers": 0,
        "files_created": [],
    }


def imports_config(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("src.config") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "src.config" or module.endswith(".config"):
                return True
            if node.level and module == "config":
                return True
            if module == "src" and any(alias.name == "config" for alias in node.names):
                return True
    return False


def test_only_main_reads_the_config():
    sources = [REPO_ROOT / "main.py", *(REPO_ROOT / "src").rglob("*.py")]

    readers = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sources
        if path.name != "config.py" and imports_config(path)
    ]

    assert readers == ["main.py"]


def test_logger_writes_where_the_caller_says_even_if_root_is_configured(
    tmp_path, extraction_logger
):
    # Stands in for logging.basicConfig() in a notebook. Before the fix,
    # hasHandlers() saw this root handler and nothing was ever attached.
    root_handler = logging.NullHandler()
    logging.getLogger().addHandler(root_handler)
    try:
        log_file = tmp_path / "logs" / "run.log"

        configure_extraction_logger(str(log_file))
        extraction_logger.info("hello from a caller-chosen path")
    finally:
        logging.getLogger().removeHandler(root_handler)

    assert "hello from a caller-chosen path" in log_file.read_text(encoding="utf-8")


def test_configuring_the_logger_twice_does_not_duplicate_handlers(
    tmp_path, extraction_logger
):
    configure_extraction_logger(str(tmp_path / "run.log"))
    configure_extraction_logger(str(tmp_path / "run.log"))

    assert len(extraction_logger.handlers) == 2  # one file, one console
