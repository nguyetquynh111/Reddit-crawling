import asyncio
import requests
import csv
import random, time
import json
from playwright.async_api import async_playwright

USER_NAME = ""
PASSWORD = ""
SUBREDDIT_URL = "https://www.reddit.com/r/nus/search/?q=chatgpt&cId=b38deca3-6150-4b69-a118-f9396075b466&iId=d05fef90-4711-4817-9681-8dc100ea0544"

def extract_post(url, headers):
    post_id = url.rstrip("/").split("/")[-2]
    api = f"https://www.reddit.com/comments/{post_id}.json?raw_json=1"

    # ---- request với retry ----
    for attempt in range(3):
        delay = random.uniform(2, 5)
        print(f"⏳ Request {api} (attempt {attempt+1}) … sleep {delay:.2f}s")
        time.sleep(delay)

        r = requests.get(api, headers=headers, timeout=30)

        if r.status_code != 200:
            print(f"❌ status {r.status_code}, text: {r.text[:100]}")
            continue

        try:
            data = r.json()
            break   # thoát loop nếu parse JSON ok
        except Exception as e:
            print(f"❌ JSON decode fail: {e}")
            print(r.text[:120])
            data = None
            continue
    else:
        print(f"❌ Failed after retries: {url}")
        return

    # ---- post ----
    post = data[0]["data"]["children"][0]["data"]
    with open("post.csv","a",newline="",encoding="utf-8") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(["id","title","body","flair","created_utc",
                        "author","score","upvote_ratio","num_comments"])
        w.writerow([
            post["id"], post.get("title",""), post.get("selftext",""),
            post.get("link_flair_text",""), post.get("created_utc",0),
            post.get("author",""), post.get("score",0),
            post.get("upvote_ratio",0.0), post.get("num_comments",0)
        ])

    # ---- comments ----
    comments=[]
    def walk(children):
        for c in children:
            if c.get("kind") != "t1": 
                continue
            d = c["data"]
            comments.append([
                d["id"], d.get("parent_id",""), d.get("body",""),
                d.get("link_id",""), d.get("created_utc",0),
                d.get("author",""), d.get("score",0),
                d.get("author","") == post.get("author","")
            ])
            if isinstance(d.get("replies"), dict):
                walk(d["replies"]["data"]["children"])
    walk(data[1]["data"]["children"])

    with open("comment.csv","a",newline="",encoding="utf-8") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(["id","parent_id","body","link_id",
                        "created_utc","author","score","is_op"])
        w.writerows(comments)

    print(f"✔ Saved post {post['id']} + {len(comments)} comments")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  
        context = await browser.new_context()

        page = await context.new_page()
        await page.goto("https://www.reddit.com/login")

        await page.fill('input[name="username"]', USER_NAME)
        await page.fill('input[name="password"]', PASSWORD)
        await page.get_by_role("button", name="Log In").click()

        # chờ random cho tự nhiên
        delay = random.uniform(3, 6)
        print(f"⏳ Waiting {delay:.2f}s after login…")
        await page.wait_for_timeout(delay * 1000)

        # lưu cookie
        cookies = await context.cookies()
        with open("cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        print("✅ Cookies saved to cookies.json")

        print(await page.title())

        with open("cookies.json", "r", encoding="utf-8") as f:
            cookies = json.load(f)

        # tìm reddit_session
        reddit_cookie = None
        for c in cookies:
            if c["name"] == "reddit_session":
                reddit_cookie = f"reddit_session={c['value']}"
                break
        if not reddit_cookie:
            raise RuntimeError("⚠️ Cookie reddit_session không tìm thấy trong cookies.json")

        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": reddit_cookie
        }

        # bắt đầu crawl
        time.sleep(random.uniform(1, 3))
        await page.goto(SUBREDDIT_URL)

        seen = set()
        last_count = -1

        while True:
            # scroll xuống
            await page.mouse.wheel(0, 4000)
            time.sleep(random.uniform(1, 3))
            await page.wait_for_timeout(1500)

            anchors = await page.locator('a[data-testid="post-title"]').all()
            for a in anchors:
                href = await a.get_attribute("href")
                if href and "/comments/" in href:
                    url = "https://www.reddit.com" + href
                    if url not in seen:          # chỉ extract link mới
                        seen.add(url)
                        print("Extract:", url)
                        extract_post(url, headers)
                        # nghỉ random cho an toàn
                        time.sleep(random.uniform(2, 5))

            # nếu sau 1 vòng không có link mới thì dừng
            if len(seen) == last_count:
                print("⚠️ Hết post để crawl.")
                break
            else:
                last_count = len(seen)
                print(f"Đã extract tổng cộng {len(seen)} post...")


        browser.close()

asyncio.run(main())
