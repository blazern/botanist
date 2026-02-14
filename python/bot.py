import asyncio
import logging
import sys
from os import getenv
from pathlib import Path

from html import escape as html_escape
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import illness_schedule
import llm

TOKEN = getenv("TELEGRAM_BOT_TOKEN")
ILLNESS_SCHEDULE_DIR = Path(getenv("ILLNESS_SCHEDULE_DIR")).resolve()
OPENAI_API_KEY = getenv("OPENAI_API_KEY")

MSG_NO_RELEVANT_ARTICLE = "Подходящие статьи не найдены"

dp = Dispatcher()

TELEGRAM_MAX_LEN = 4096

async def _send_in_chunks(message: Message, text: str) -> None:
    """
    Telegram hard-limits message size: https://core.telegram.org/bots/api#sendmessage
    Send as multiple messages if needed.
    """
    if len(text) <= TELEGRAM_MAX_LEN:
        await message.answer(text)
        return

    # Split by lines to avoid breaking HTML entities too much.
    lines = text.splitlines(keepends=True)
    buf = ""
    for line in lines:
        if len(buf) + len(line) > TELEGRAM_MAX_LEN:
            if buf:
                await message.answer(buf)
                buf = ""
            # If a single line is huge, hard-split it.
            while len(line) > TELEGRAM_MAX_LEN:
                await message.answer(line[:TELEGRAM_MAX_LEN])
                line = line[TELEGRAM_MAX_LEN:]
        buf += line
    if buf:
        await message.answer(buf)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    response = """
Этот бот попытается помочь тебе определить, к каким статьям Расписания Болезней относятся твои диагнозы.
Просто отправь диагнозы или описание симптомов следующим сообщением.
"""
    await message.answer(response)


@dp.message(Command("article"))
async def article_handler(message: Message) -> None:
    """
    Usage:
      /article 57
    """
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /article <number>\nExample: /article 57")
        return

    number = parts[1].strip()

    try:
        result = illness_schedule.get_article_text(number, ILLNESS_SCHEDULE_DIR)
        reply = (
            f'{html.link("Article link", result.url)}\n'
            f"{html.quote(result.text)}"
        )
        await _send_in_chunks(message, reply)
    except ValueError as e:
        logging.exception("Input exception", exc_info=e)
        await message.answer(f"Неверный ввод: {html.quote(str(e))}")
    except FileNotFoundError as e:
        logging.exception("No article", exc_info=e)
        await message.answer("Статья не найдена")
    except RuntimeError as e:
        logging.exception("Unknown error", exc_info=e)
        await message.answer(f"Внутренняя ошибка: {html.quote(str(e))}")


@dp.message()
async def llm_article_search(message: Message) -> None:
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer(MSG_NO_RELEVANT_ARTICLE)
        return

    await message.answer(f"Обрабатываю запрос")

    try:
        found_any = False

        results = await asyncio.to_thread(
            llm.find_relevant_articles,
            user_medical_condition=user_text,
            illness_schedule_dir=ILLNESS_SCHEDULE_DIR,
            openai_key=OPENAI_API_KEY,
        )
        for item in results:
            found_any = True
            await _send_in_chunks(message, _format_article(item))

        if not found_any:
            await message.answer(MSG_NO_RELEVANT_ARTICLE)

    except Exception as e:
        logging.exception("LLM article search failed", exc_info=e)
        await message.answer(f"Внутренняя ошибка: {html.quote(str(e))}")


def _format_article(item: llm.RelevantArticleData) -> str:
    """
    Format RelevantArticleData into:

    <ARTICLE_HEADER>
    <ARTICLE_URL>
    <ARTICLE_RELEVANCE_REASONING>
    Relevant parts:
    <TELEGRAM_QUOTE1>
    <TELEGRAM_QUOTE2>
    ...
    """

    if item.article.url:
        header = f"{item.article_number}. {html_escape(item.article_header)}"
        url_line = html.link(header, item.article.url)
    else:
        url_line = ""

    reasoning = (item.reasoning or "").strip()
    reasoning_line = html_escape(reasoning) if reasoning else ""

    quote_blocks = []
    for quote in item.quotes or []:
        quote_blocks.append(f"<pre>{html_escape(quote.strip())}</pre>\n")

    parts = [
        url_line,
        "\n",
        reasoning_line,
        "\n"
        "Возможно релевантные цитаты статьи:",
        *quote_blocks,
    ]

    text = "\n".join(part for part in parts if part)
    return text


async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
