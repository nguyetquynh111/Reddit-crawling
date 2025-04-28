#!/usr/bin/env python
# reddit_playwright_export.py
"""
Scrape a subreddit with Playwright, filter by keywords, save as:
  1) CSV (tabular, first-comment view)
  2) Hierarchical folder of JSON objects with all comments and replies
"""

import json, re, unicodedata, pathlib, datetime
from urllib.parse import urljoin
from tqdm import tqdm
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ─────────────────────────── USER SETTINGS ──────────────────────────── #
SUBREDDIT_URL = "https://www.reddit.com/r/webscraping/"
KEYWORDS      = ["OpenAI", "GPT", "Learning"]       # case-insensitive
MAX_POSTS     = 200          # open at most this many post pages
SCROLLS       = 5           # number of on-homepage scrolls for more links
HEADLESS      = True        # set False to watch the browser
CSV_PATH      = "reddit_posts_and_first_comments.csv"
JSON_BASEDIR  = pathlib.Path("data")                # folder root
MIN_POSTS = 100
# ─────────────────────────────────────────────────────────────────────── #


def contains_keywords(text: str, keywords: list) -> bool:
    txt = text.lower()
    return any(k.lower() in txt for k in keywords)


def slugify(title: str, max_len: int = 100) -> str:
    """
    File-system-safe slug from title.
    Keeps a–z, 0–9, dash, underscore.  Truncates to `max_len` chars.
    """
    title = (
        unicodedata.normalize("NFKD", title)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    title = re.sub(r"[^a-z0-9]+", "-", title).strip("-")
    return title[:max_len] or "untitled"


def extract_post(page, root_id: str) -> dict | None:
    """
    Parse the fully-rendered HTML of a single post page and return a dict
    containing the fields we care about *plus* any extra keys you might want.
    """
    soup = BeautifulSoup(page.content(), "html.parser")

    root = soup.find("shreddit-post")
    if not root:
        return None                                   # skip ads / removed posts

    # ── title ──────────────────────────────────────────────────────────
    title = root.get("post-title") or soup.select_one("shreddit-title")
    if not isinstance(title, str):
        title = title.get("title", "")
    title = title.strip()

    # ── body (choose the <div … id="t3_xxx-post-rtjson-content" class=md …>) ─
    body_div = (
        soup.select_one('div[id$="-post-rtjson-content"].md')
        or soup.select_one(
            f'div[id^="{root["id"]}"][id$="-post-rtjson-content"]'
        )
    )
    body_text = body_div.get_text(" ", strip=True) if body_div else ""

    # ── all comments (depth="0" for answers, and nested comments for replies) ───────────────────────────────────────
    all_comments = []
    top_level_comments = soup.find_all("shreddit-comment", {"depth": "0"})  # all answers
    for comment in top_level_comments:
        user = comment.get("author", "")
        body_div = comment.find(id=re.compile(r"-comment-rtjson-content"))
        comment_text = body_div.get_text(" ", strip=True) if body_div else ""
        replies = extract_replies(comment)  # get replies for this comment
        all_comments.append({
            "user": user,
            "comment": comment_text,
            "replies": replies  # include all replies here
        })

    return {
        # core
        "subreddit":          root.get("subreddit-name", ""),
        "post_id":            root.get("id", ""),
        "permalink":          urljoin("https://www.reddit.com", root.get("permalink", page.url)),
        "created_utc":        root.get("created-timestamp", ""),
        "author":             root.get("author", ""),
        "title":              title,
        "body":               body_text,
        # all comments and replies
        "all_comments":       all_comments,
        # scrape metadata
        "scraped_at":         datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds") + "Z",
    }


def extract_replies(comment) -> list:
    """
    Extract all replies to a given top-level comment (nested replies).
    """
    replies = []
    nested_comments = comment.find_all("shreddit-comment", {"depth": "1"})  # replies are usually depth 1 or greater
    for reply in nested_comments:
        user = reply.get("author", "")
        body_div = reply.find(id=re.compile(r"-comment-rtjson-content"))
        reply_text = body_div.get_text(" ", strip=True) if body_div else ""
        replies.append({
            "user": user,
            "comment": reply_text
        })
    return replies

def scrape_subreddit(
    subreddit_url: str,
    keywords: list,
    max_posts: int,
    scrolls: int,
    headless: bool,
    min_posts: int
) -> list[dict]:
    """
    Main scraper: visit subreddit front page, gather post links,
    open each post page, parse it.
    """
    records: list[dict] = []
    matched_posts: int = 0  # Counter to track how many posts contain the keyword
    scraped_posts: int = 0  # Counter to track the total number of posts scraped

    with sync_playwright() as pw:
        browser = pw.firefox.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        page.goto(subreddit_url, timeout=60_000)
        page.wait_for_load_state("networkidle")

        # ── Loop to keep scraping until we reach the minimum posts or max posts ───────
        while matched_posts < min_posts and scraped_posts < max_posts:
            # Scroll if there are not enough posts
            if scraped_posts < max_posts:
                for _ in range(scrolls):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(1_000)

            # ── Loop through available post links after scrolling ───────────────
            links = page.locator('a[slot="full-post-link"]')
            n_links = min(links.count(), max_posts - scraped_posts)

            for i in range(n_links):
                if matched_posts >= min_posts:
                    break  # Stop if we have reached the minimum posts

                href = links.nth(scraped_posts).get_attribute("href") or ""
                question_text = links.nth(scraped_posts).locator("faceplate-screen-reader-content").inner_text()

                # ── NEW EARLY FILTER ────────────────────────────────────────────────
                if not contains_keywords(href, keywords) and not contains_keywords(question_text, keywords):
                    scraped_posts += 1
                    continue   # skip post early, don't even open it
                # ────────────────────────────────────────────────────────────────────

                full_url = urljoin("https://www.reddit.com", href)
                post_tab = context.new_page()
                post_tab.goto(full_url, timeout=60_000)
                post_tab.wait_for_load_state("networkidle")

                post = extract_post(post_tab, root_id=href)
                post_tab.close()

                if not post:
                    scraped_posts += 1
                    continue

                # Keep posts whose title/body contain keywords
                if contains_keywords(post['title'] + " " + post['body'], keywords):
                    records.append(post)
                    matched_posts += 1  # Increment when a post matches the keyword

                scraped_posts += 1  # Increment the total scraped posts

            # If not enough posts matched, keep scrolling and retry
            if matched_posts < min_posts:
                print(f"Not enough posts found. Scrolling for more...")

            # Break the loop if we've reached the maximum posts
            if scraped_posts >= max_posts:
                break

        browser.close()

    return records


def save_outputs(records: list[dict], csv_path: str, json_basedir: pathlib.Path):
    # 1) CSV / pandas table  (title, body, first-comment quick view)
    df = pd.DataFrame(
        [{
            "post_id":  r["post_id"],
            "subreddit": r["subreddit"],
            "created_utc": r["created_utc"],
            "author":  r["author"],
            "title":   r["title"],
            "body":    r["body"],
            # Remove first_comment_user and first_comment_text since we now have all comments
            "permalink": r["permalink"],
        } for r in records]
    )
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"✔ CSV   → {csv_path}  ({len(df)} rows)")

    # 2) per-post JSON  data/<subreddit>/<slug>/post_id.json
    json_basedir.mkdir(exist_ok=True)
    for r in records:
        slug   = slugify(r["title"])
        subdir = json_basedir / r["subreddit"] / slug
        subdir.mkdir(parents=True, exist_ok=True)

        with open(subdir / f"{r['post_id']}.json", "w", encoding="utf-8") as fp:
            json.dump(r, fp, ensure_ascii=False, indent=2)

    print(f"✔ JSONs → {json_basedir}/<sub>/<slug>/<id>.json")



# posts = scrape_subreddit()
# save_outputs(posts)
