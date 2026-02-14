from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_ARTICLE_RE = re.compile(r"^(?:[1-9]\d{0,2})$")  # 1..999

@dataclass
class Article:
    url: str
    text: str

@dataclass
class ArticleHeader:
    number: int
    text: str

def get_article_text(number: str, base_dir: Path) -> Article:
    """
    Return article markdown text for `number` from `base_dir/{number}.md`.
    """
    if not _ARTICLE_RE.match(number):
        raise ValueError(f"Invalid article number: {number}")

    article = _resolve_file(base_dir, f"{number}.md")
    file_text = article.read_text(encoding="utf-8")
    url, _, text = file_text.partition("\n")
    return Article(url, text)

def get_articles_headers(base_dir: Path) -> list[ArticleHeader]:
    """
    Return articles headers, where the first item in the tuple is the number
    of the article, and the second one is its header.
    """
    headers = _resolve_file(base_dir, "headers.md")
    file_text = headers.read_text(encoding="utf-8")
    result = list()
    for i, text in enumerate(file_text.split('\n')):
        result.append(ArticleHeader(i + 1, text))
    return result

def _resolve_file(base_dir: Path, file_name: str) -> Path:
    base = Path(base_dir).resolve()
    if not base.exists() or not base.is_dir():
        raise RuntimeError(f"Base dir is invalid or missing: {base}")

    candidate = (base / file_name).resolve()
    # Prevent path traversal / symlink escapes
    # e.g. /app/data/illness_schedule/../../../../etc/passwd.md
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise RuntimeError("Invalid file path") from e

    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"File file found: {file_name}")

    return candidate
