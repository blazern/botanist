import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from openai import OpenAI

import illness_schedule
from illness_schedule import Article

CHAT_GPT_MODEL = "gpt-5-nano-2025-08-07"

CHAT_GPT_INSTRUCTION_SELECT_ARTICLES = """
You are given a JSON object with:
- "user_medical_condition": a description of medical conditions
- "articles_headers": a list of article numbers and their headers from the official Russian Army illness schedule.

Your task:
Select all article numbers whose headers could reasonably correspond to the medical conditions described.

Rules:
- Use only the article numbers provided in "articles_headers".
- Do not invent new article numbers.
- Consider medical synonyms and related terminology.
- If there is reasonable medical relevance, include the article.
- If unsure but there is plausible connection, do not include it.
- Do not include articles that are clearly unrelated.

Output format:
Return ONLY valid JSON in the following format:

{ "articles_numbers": [N1, N2, ...] }

Do not include explanations or any additional text.
Order articles_numbers in the relevance order.
"""

CHAT_GPT_INSTRUCTION_FIND_QUOTES = """
You are given a JSON object with:
- "user_medical_condition": free-text description of conditions/symptoms
- "article_text": the full text of ONE article from the official Russian Army illness schedule

Task:
Decide whether the article_text contains criteria relevant to the user_medical_condition.
If yes, extract verbatim quotes (contiguous spans) from article_text that support the relevance.

Rules:
- Use ONLY article_text for quotes. Do not add or paraphrase any quoted content.
- Matching may use medical synonyms/related terms, but quotes must be verbatim from article_text.
- Extract the smallest contiguous span(s) that contain the relevant criterion.
- Do NOT stitch non-adjacent fragments into one quote.
- If uncertain but plausibly relevant, include the quote.
- If not relevant, return an empty quotes list.

Limits:
- Each quote must be at most 600 characters (trim to the minimal relevant part).

Output:
Return ONLY valid JSON:
{ "quotes": [...], "reasoning": "very short reasoning of relevance" }

If quotes is empty, set reasoning to empty string.
Reasoning must be in Russian language.
Ensure JSON escaping is correct; newlines are allowed as \n.
"""

@dataclass
class RelevantArticleData:
    article: Article
    article_number: int
    article_header: str
    reasoning: str
    quotes: list[str]

def find_relevant_articles(
        user_medical_condition: str,
        illness_schedule_dir: Path,
        openai_key: str,
) -> Generator[RelevantArticleData, None, None]:
    """
    Yields LLM replies with relevant articles to the user medical condition.
    """
    chatgpt_client = OpenAI(api_key=openai_key)

    articles_headers = illness_schedule.get_articles_headers(illness_schedule_dir)
    articles_headers_input = {
        "user_medical_condition": user_medical_condition,
        "articles_headers": [{ "number": header.number, "header": header.text } for header in articles_headers],
    }
    articles_numbers_response = chatgpt_client.responses.create(
        instructions=CHAT_GPT_INSTRUCTION_SELECT_ARTICLES,
        input=json.dumps(articles_headers_input),
        model=CHAT_GPT_MODEL,
    )
    articles_numbers_json = json.loads(articles_numbers_response.output_text)
    article_numbers = articles_numbers_json["articles_numbers"]

    articles_headers_map = {header.number: header.text for header in articles_headers}

    for article_number in article_numbers:
        article = illness_schedule.get_article_text(str(article_number), illness_schedule_dir)
        input_artile = {
            "user_medical_condition": user_medical_condition,
            "article_text": article.text,
        }

        quotes_response = chatgpt_client.responses.create(
            instructions=CHAT_GPT_INSTRUCTION_FIND_QUOTES,
            input=json.dumps(input_artile),
            model=CHAT_GPT_MODEL,
        )
        quotes_json = json.loads(quotes_response.output_text)

        quotes = quotes_json["quotes"]
        if len(quotes) == 0:
            continue

        yield RelevantArticleData(
            article=article,
            article_number=article_number,
            article_header=articles_headers_map[article_number],
            reasoning=quotes_json["reasoning"],
            quotes=quotes_json["quotes"],
        )
