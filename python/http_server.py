from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field
from pathlib import Path
import os
import logging
from typing import List, Optional

import illness_schedule
import llm

app = FastAPI()

ILLNESS_SCHEDULE_DIR = Path(os.getenv("ILLNESS_SCHEDULE_DIR")).resolve()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class LlmArticleSearchRequest(BaseModel):
    illness_description: str = Field(min_length=1, description="User illness/symptoms description")

class LlmArticleSearchItem(BaseModel):
    article_number: str
    article_header: str
    article_url: Optional[str] = None
    reasoning: str
    quotes: List[str]

@app.get("/article/{number}", response_class=HTMLResponse)
async def article(number: str) -> str:
    try:
        result = illness_schedule.get_article_text(number, ILLNESS_SCHEDULE_DIR)
        return f"""
        <a href="{result.url}">Article link</a>
        <pre>{result.text}</pre>
        """
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")


@app.post("/llm-article-search", response_model=List[LlmArticleSearchItem])
async def llm_article_search_endpoint(payload: LlmArticleSearchRequest):
    user_text = payload.illness_description.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="illness_description must not be empty")

    results: List[LlmArticleSearchItem] = []

    try:
        async for item in llm.find_relevant_articles(
            user_medical_condition=user_text,
            illness_schedule_dir=ILLNESS_SCHEDULE_DIR,
            openai_key=OPENAI_API_KEY,
        ):
            results.append(
                LlmArticleSearchItem(
                    article_number=str(item.article_number),
                    article_header=item.article_header or "",
                    article_url=item.article.url,
                    reasoning=(item.reasoning or "").strip(),
                    quotes=item.quotes or [],
                )
            )
        return results

    except ValueError as e:
        logging.exception("llm-article-search failed", exc_info=e)
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        logging.exception("llm-article-search failed", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Missing file: {e}")
    except Exception as e:
        logging.exception("llm-article-search failed", exc_info=e)
        raise HTTPException(status_code=500, detail="Internal error")
