from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pathlib import Path
import os
import re

app = FastAPI()

ARTICLE_RE = re.compile(r"^(?:[1-9]\d{0,2})$")  # 1..999

def _get_articles_dir() -> Path:
    illness_schedule_dir = Path(os.getenv("ILLNESS_SCHEDULE_DIR")).resolve()
    if not illness_schedule_dir.exists() or not illness_schedule_dir.is_dir():
        raise RuntimeError(f"ILLNESS_SCHEDULE_DIR is invalid or missing: {illness_schedule_dir}")
    return illness_schedule_dir

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "Hello World"

@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

@app.get("/article/{number}", response_class=PlainTextResponse)
async def article(number: str) -> str:
    if not ARTICLE_RE.match(number):
        raise HTTPException(status_code=400, detail=f"Invalid article number: {number}")

    base = _get_articles_dir()
    article = (base / f"{number}.md").resolve()

    # Prevent path traversal / symlink escapes
    # e.g. /app/data/illness_schedule/../../../../etc/passwd.md
    try:
        article.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid article path")

    if not article.exists() or not article.is_file():
        raise HTTPException(status_code=404, detail="Article not found")

    return article.read_text(encoding="utf-8")
