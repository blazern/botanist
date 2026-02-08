#!/usr/bin/env python3
"""
NOTE: all the code here is LLM-generated and is not checked or edited, because
its entire purpose is to give the articles just once and store them in the repo 

Scrape https://netprizyvu.ru/raspisanie-bolezney into Markdown files.

Pipeline:
1) From INDEX_URL collect "disease pages" links that start with /diseases/ (category/section pages).
2) Open each disease page and collect links whose visible text matches /^Статья N.../ .
   Those are the actual article pages (88 of them).
3) For each article page:
   - Extract only the article content (table + explanatory blocks)
   - Convert table to Markdown keeping ONLY 3 columns:
       (Статья расписания болезней, Наименование..., Категория... (I графа))
     and skipping the "I графа | II графа | III графа" row.
   - Save to output dir as "{N}.md"
   - FIRST LINE of each .md is the original article URL
4) Print all saved file paths at the end (stdout).
   Progress goes to stderr (very verbose).

Usage:
  python3 scraper.py /path/to/output_dir
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

INDEX_URL = "https://netprizyvu.ru/raspisanie-bolezney"
DISEASE_PREFIX = "https://netprizyvu.ru/diseases/"

ARTICLE_TEXT_RE = re.compile(r"^\s*Статья\s+(\d+)\b.*", re.IGNORECASE)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }
    )
    return s


def fetch_text(session: requests.Session, url: str, timeout: int = 30) -> str:
    log(f"      HTTP GET {url}")
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_text(session, url), "lxml")


def clean_url(url: str) -> str:
    p = urlparse(url)
    return p._replace(query="", fragment="").geturl()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# -----------------------
# Step 1: discover pages
# -----------------------
def extract_disease_pages_from_index(session: requests.Session) -> list[str]:
    soup = get_soup(session, INDEX_URL)
    links: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = clean_url(urljoin(INDEX_URL, a["href"]))
        if href.startswith(DISEASE_PREFIX):
            links.add(href)

    return sorted(links)


def extract_article_links_from_disease_page(
    session: requests.Session, disease_page_url: str
) -> list[tuple[int, str, str]]:
    soup = get_soup(session, disease_page_url)
    found: dict[int, tuple[str, str]] = {}

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text:
            continue

        m = ARTICLE_TEXT_RE.match(text)
        if not m:
            continue

        n = int(m.group(1))
        href = clean_url(urljoin(disease_page_url, a["href"]))
        found.setdefault(n, (text, href))

    out = [(n, t, u) for n, (t, u) in found.items()]
    out.sort(key=lambda x: x[0])
    return out


def discover_all_article_urls(session: requests.Session, sleep_s: float = 0.2) -> list[tuple[int, str, str]]:
    log("[1/4] Discovering disease pages from index...")
    disease_pages = extract_disease_pages_from_index(session)
    log(f"      Found {len(disease_pages)} disease pages on index")

    all_articles: dict[int, tuple[str, str]] = {}

    log("[2/4] Discovering article links by visiting disease pages...")
    for i, page in enumerate(disease_pages, start=1):
        log(f"    Disease page ({i}/{len(disease_pages)}): {page}")
        try:
            triples = extract_article_links_from_disease_page(session, page)
            log(f"      Found {len(triples)} article links on this page")
            for n, title, url in triples:
                all_articles.setdefault(n, (title, url))
        except requests.RequestException as e:
            log(f"      WARN: failed to fetch {page}: {e}")
        time.sleep(sleep_s)

    articles = [(n, t, u) for n, (t, u) in all_articles.items()]
    articles.sort(key=lambda x: x[0])

    log(f"      Total unique articles discovered: {len(articles)}")
    if articles:
        log(f"      Article number range: {articles[0][0]}..{articles[-1][0]}")
    return articles


# -----------------------
# Step 2: parse articles
# -----------------------
def html_table_to_markdown(table: Tag) -> str:
    out_rows: list[list[str]] = []

    for tr in table.select("tr"):
        cells = tr.find_all(["th", "td"])
        row = [normalize_ws(c.get_text(" ", strip=True).replace("\xa0", " ")) for c in cells]
        if not row:
            continue

        if len(row) == 3 and row[0].lower().startswith("i графа"):
            continue

        if len(row) == 3 and row[0].lower().startswith("статья расписания болезней"):
            continue

        if len(row) >= 5:
            out_rows.append([row[0], row[1], row[2]])
            continue

        if len(row) == 4:
            out_rows.append([row[0], "", row[1]])
            continue

        if len(row) == 3:
            out_rows.append(row[:3])
            continue

    if not out_rows:
        return ""

    header = [
        "Статья расписания болезней",
        "Наименование болезней, степень нарушения функции",
        "Категория годности к военной службе (I графа)",
    ]

    def esc(s: str) -> str:
        return s.replace("\n", " ").replace("|", "\\|").strip()

    md: list[str] = []
    md.append("| " + " | ".join(header) + " |")
    md.append("| --- | --- | --- |")
    for r in out_rows:
        r = (r + ["", "", ""])[:3]
        md.append("| " + " | ".join(esc(x) for x in r) + " |")
    return "\n".join(md)


def render_list(lst: Tag, indent: int = 0) -> list[str]:
    out: list[str] = []

    for li in lst.find_all("li", recursive=False):
        text_parts: list[str] = []
        for child in li.contents:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                continue
            if isinstance(child, (Tag, NavigableString)):
                txt = child.get_text(" ", strip=True) if isinstance(child, Tag) else str(child)
                text_parts.append(txt)

        line = normalize_ws(" ".join(text_parts).replace("\xa0", " "))
        if line:
            out.append(("  " * indent) + f"- {line}")

        for nested in li.find_all(["ul", "ol"], recursive=False):
            out.extend(render_list(nested, indent + 1))

    return out


def pick_root_container(soup: BeautifulSoup) -> Tag:
    section = soup.select_one("section.currentdisease")
    if not section:
        return soup.body or soup  # type: ignore

    content = section.select_one(".currentdisease__content") or section
    wrapper = content.select_one(".currentdisease__wrapper") or content
    return wrapper


def extract_section_title(soup: BeautifulSoup) -> str:
    h1 = soup.select_one("section.currentdisease h1")
    return normalize_ws(h1.get_text(" ", strip=True)) if h1 else ""


def extract_article_title_from_page(soup: BeautifulSoup) -> str:
    subtitle = soup.select_one(".title__wrapper--subtitle .DefIcoText__text")
    if subtitle:
        return normalize_ws(subtitle.get_text(" ", strip=True))
    found = soup.find(string=re.compile(r"Статья\s+\d+", re.I))
    return normalize_ws(str(found)) if found else ""


def extract_article_markdown_from_html(page_html: str, fallback_title: str, article_url: str) -> str:
    soup = BeautifulSoup(page_html, "lxml")

    section_title = extract_section_title(soup)
    article_title = extract_article_title_from_page(soup) or fallback_title

    parts: list[str] = []

    # REQUIRED: first line is the original URL
    parts.append(article_url)
    parts.append("")  # blank line

    if article_title:
        parts.append(f"# {article_title}")
        parts.append("")
    if section_title:
        parts.append(f"**{section_title}**")
        parts.append("")

    root = pick_root_container(soup)

    for child in root.children:
        if not isinstance(child, Tag):
            continue

        table = child if child.name == "table" else child.find("table")
        if table:
            md_table = html_table_to_markdown(table)
            if md_table:
                parts.append(md_table)
                parts.append("")
            continue

        classes = set(child.get("class", []))

        if "information__maintitle" in classes:
            title = normalize_ws(child.get_text(" ", strip=True))
            if title:
                parts.append(f"## {title}")
                parts.append("")
            continue

        if "information__text" in classes:
            for inner in child.children:
                if not isinstance(inner, Tag):
                    continue

                if inner.name == "p":
                    txt = normalize_ws(inner.get_text(" ", strip=True))
                    if txt:
                        parts.append(txt)
                        parts.append("")
                elif inner.name in ("ul", "ol"):
                    lines = render_list(inner)
                    if lines:
                        parts.extend(lines)
                        parts.append("")
                else:
                    txt = normalize_ws(inner.get_text(" ", strip=True))
                    if txt:
                        parts.append(txt)
                        parts.append("")

    md = "\n".join(parts)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md


# -----------------------
# Main
# -----------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("output_dir", help="Directory for .md files")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep between requests (seconds)")
    ap.add_argument("--expected", type=int, default=88, help="Expected number of articles (warning only)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    failures: list[tuple[int, str, str]] = []

    with make_session() as session:
        articles = discover_all_article_urls(session, sleep_s=args.sleep)

        if len(articles) != args.expected:
            log(f"      WARN: discovered {len(articles)} articles; expected {args.expected}")

        log("[3/4] Fetching + parsing article pages...")
        total = len(articles)

        for idx, (n, title, url) in enumerate(articles, start=1):
            log(f"    Article ({idx}/{total}) #{n}: {url}")

            try:
                page_html = fetch_text(session, url)
                log("      Parsing HTML -> Markdown")
                md = extract_article_markdown_from_html(page_html, fallback_title=title, article_url=url)

                path = out_dir / f"{n}.md"
                log(f"      Writing {path}")
                path.write_text(md, encoding="utf-8")
                saved_paths.append(path)
                log("      OK")
            except Exception as e:
                log(f"      WARN: failed article #{n} ({url}): {e}")
                failures.append((n, title, url))

            time.sleep(args.sleep)

    log("[4/4] Finished\n")

    for p in sorted(saved_paths, key=lambda x: int(x.stem) if x.stem.isdigit() else 10**9):
        print(str(p))

    log(f"Saved {len(saved_paths)} files to {out_dir}")
    if failures:
        log(f"Failures: {len(failures)}")
        for n, title, url in failures[:30]:
            log(f"  - #{n} {title} -> {url}")
        if len(failures) > 30:
            log("  ... (more failures omitted)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
