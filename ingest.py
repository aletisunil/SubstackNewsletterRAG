from substack_api import Newsletter
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime
from pathlib import Path
import re
import os
import argparse


def safe_get(obj, attr, default=None):
    if obj is None:
        return default

    # method: obj.attr()
    method = getattr(obj, attr, None)
    if callable(method):
        try:
            value = method()
            if value is not None:
                return value
        except Exception:
            pass

    # attribute: obj.attr
    try:
        value = getattr(obj, attr, None)
        if value is not None:
            return value
    except Exception:
        pass

    # dict: obj[attr]
    if isinstance(obj, dict):
        value = obj.get(attr, default)
        if value is not None:
            return value

    return default


def object_to_dict(obj):
    """
    Best-effort conversion of library objects into dicts.
    """
    if obj is None:
        return {}

    if isinstance(obj, dict):
        return obj

    # Try common object storage
    try:
        if hasattr(obj, "__dict__"):
            return {
                k: v for k, v in vars(obj).items()
                if not k.startswith("_")
            }
    except Exception:
        pass

    return {}



def clean_html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    clean_html = str(soup)
    markdown = md(clean_html, heading_style="ATX")

    # cleanup
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"^\#\s+\*\*(.*?)\*\*$", r"# \1", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^\#\#\s+\*\*(.*?)\*\*$", r"## \1", markdown, flags=re.MULTILINE)
    markdown = markdown.strip()

    return markdown


def format_date(value) -> str:
    if value is None or value == "":
        return ""

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()

    # unix timestamp
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text)).strftime("%Y-%m-%d")
        except Exception:
            pass

    # ISO-like string
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return text


def yaml_escape(value) -> str:
    if value is None:
        return '""'
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def sanitize_filename(name: str, fallback: str = "post") -> str:
    text = (name or "").strip()
    if not text:
        text = fallback
    text = re.sub(r'[<>:"/\\|?*]+', "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:150]


def extract_metadata_from_html(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")

    def get_meta(*names):
        for name in names:
            tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    canonical_url = ""
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = canonical_tag["href"].strip()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    h1 = soup.find("h1")
    if not title and h1:
        title = h1.get_text(" ", strip=True)

    post_date = ""
    time_tag = soup.find("time")
    if time_tag:
        post_date = time_tag.get("datetime", "").strip() or time_tag.get_text(" ", strip=True)

    return {
        "canonical_url": canonical_url,
        "title": title,
        "description": get_meta("description", "og:description", "twitter:description"),
        "post_date": post_date,
    }


def extract_post_record(post) -> dict:

    body_html = (
        safe_get(post, "body_html", "")
    )

    title = (
        safe_get(post, "title", "")
    )

    description = (
        safe_get(post, "description", "")
    )

    canonical_url = (
        safe_get(post, "canonical_url", "")
    )

    slug = (
        safe_get(post, "slug", "")
    )

    post_date = (
        safe_get(post, "post_date", "")
    )

    body_markdown = clean_html_to_markdown(body_html)

    return {
        "canonical_url": canonical_url or "",
        "slug": slug or "",
        "post_date": post_date,
        "title": title or "",
        "description": description or "",
        "body_html": body_html or "",
        "body_markdown": body_markdown or "",
    }


def post_to_markdown(posts, output_path: str):
    if posts is None:
        return

    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not isinstance(posts, list):
        posts = list(posts)

    for idx, post in enumerate(posts, start=1):
        record = extract_post_record(post.get_metadata())

        filename_base = record["slug"] or record["title"] or f"post_{idx}"
        filename = sanitize_filename(filename_base, fallback=f"post_{idx}") + ".md"

        output = f"""---
title: {yaml_escape(record["title"])}
description: {yaml_escape(record["description"])}
date: {yaml_escape(record["post_date"])}
canonical_url: {yaml_escape(record["canonical_url"])}
slug: {yaml_escape(record["slug"])}
---

{record["body_markdown"]}
"""

        with open(output_dir / filename, "w", encoding="utf-8") as f:
            f.write(output)

        print(f"Saved: {output_dir / filename}")


def process_newsletter(base_url: str, limit: int | None = None, fetch_all: bool = False):
    newsletter = Newsletter(base_url)

    if fetch_all:
        posts = newsletter.get_posts()
    else:
        posts = newsletter.get_posts(limit=limit)

    post_to_markdown(posts, output_path="data/processed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Substack newsletter")

    parser.add_argument(
        "--base",
        type=str,
        required=True,
        help="Base Substack URL (e.g. https://warikoo.substack.com/)"
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--limit",
        type=int,
        help="Number of recent posts to fetch"
    )

    group.add_argument(
        "--all",
        action="store_true",
        help="Fetch all available posts"
    )

    args = parser.parse_args()

    try:
        if args.all:
            process_newsletter(base_url=args.base, fetch_all=True)
        else:
            process_newsletter(base_url=args.base, limit=args.limit)
    except KeyboardInterrupt:
        print("\nStopped by user.")