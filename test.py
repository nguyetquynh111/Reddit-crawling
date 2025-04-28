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
from urllib.parse import urljoin
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
    username:str,
    password:str,
    subreddit_url: str,
    keywords: list,
    max_posts: int,
    scrolls: int,
    headless: bool,
    min_posts: int
) -> list[dict]:
    """
    Visit a subreddit, keep scrolling until we collect at least
    `min_posts` that match `keywords`, or until `max_posts` total
    post pages have been opened.
    """
    records: list[dict] = []
    matched_posts: int = 0     # how many keepers we have so far
    opened_posts:  int = 0     # how many post pages we've opened in total
    processed_links: int = 0   # index of next <a> to open on the page

    def contains(text: str) -> bool:
        return any(k.lower() in text.lower() for k in keywords)

    with sync_playwright() as pw:
        browser  = pw.firefox.launch(headless=headless)
        context  = browser.new_context()
        page     = context.new_page()

        # --- LOGIN STEP ---
        page.goto("https://www.reddit.com/login/", timeout=60000)
        page.wait_for_load_state("networkidle")

        # Fill in the username and password fields
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)

        # Wait for the login button to become enabled
        login_button = page.locator('button:has-text("Log In")')
        login_button.wait_for(state="enabled", timeout=10000)

        # Click the login button
        login_button.click()

        # Wait for navigation to complete
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)

        # --- GO TO SUBREDDIT ---
        page.goto(subreddit_url, timeout=60_000)
        page.wait_for_load_state("networkidle")

        # keep going until goal reached or hard cap hit
        while matched_posts < min_posts and opened_posts < max_posts:

            # if we’ve already consumed the current batch of links, scroll for more
            links   = page.locator('a[data-testid="post-title"]')
            n_links = links.count()

            if processed_links >= n_links:                         # nothing new → scroll
                for _ in range(scrolls):
                    page.mouse.wheel(0, 2500)
                    page.wait_for_timeout(1_000)
                continue                                           # re-evaluate links after scroll

            # ── open the next unseen link ───────────────────────────────────────
            anchor = links.nth(processed_links)
            processed_links += 1            # **advance the cursor immediately**

            href = anchor.get_attribute("href") or ""
            full_url = urljoin("https://www.reddit.com", href)

            post_tab = context.new_page()
            try:
                post_tab.goto(full_url, timeout=60_000)
                post_tab.wait_for_load_state("networkidle")
            except Exception as e:
                print(f"⚠️  could not load {full_url} – {e}")
                post_tab.close()
                opened_posts += 1
                continue

            post = extract_post(post_tab, root_id=href)
            post_tab.close()
            opened_posts += 1

            if not post:
                continue

            if not contains(post["title"]) and not contains(post["body"]):
                continue                                    # skip; no keyword match

            # keep the post
            records.append(post)
            matched_posts += 1
            print(f"✔ kept {matched_posts}/{min_posts}: {post['title'][:60]}")

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