import streamlit as st
import pandas as pd
import pathlib, os, shutil, time, zipfile, tempfile
from test import scrape_subreddit, save_outputs

# ───── default UI values ──────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "subreddit_url": "https://www.reddit.com/r/webscraping/",
    "keywords":      ["OpenAI", "GPT", "Learning"],
    "max_posts":     200,
    "scrolls":       5,
    "min_posts":     100,
    "headless":      True,
    "csv_path":      "reddit_posts_and_first_comments.csv",
    "json_basedir":  pathlib.Path("data"),
}

st.set_page_config(page_title="Reddit Scraper", layout="wide")
st.title("Reddit Scraper")

# ───── sidebar inputs ─────────────────────────────────────────────────
st.sidebar.header("Scraping Settings")
subreddit_url = st.sidebar.text_input("Subreddit URL", value=DEFAULT_SETTINGS["subreddit_url"])
keywords_str  = st.sidebar.text_input("Keywords (comma-separated)", ", ".join(DEFAULT_SETTINGS["keywords"]))
max_posts     = st.sidebar.number_input("Maximum Posts", 1, value=DEFAULT_SETTINGS["max_posts"])
scrolls       = st.sidebar.number_input("Number of Scrolls", 1, value=DEFAULT_SETTINGS["scrolls"])
min_posts     = st.sidebar.number_input("Minimum Posts", 1, value=DEFAULT_SETTINGS["min_posts"])
headless      = st.sidebar.checkbox("Headless Mode", value=DEFAULT_SETTINGS["headless"])
keywords      = [k.strip() for k in keywords_str.split(",") if k.strip()]

# ───── scrape & display ───────────────────────────────────────────────
if st.sidebar.button("Start Scraping"):
    with st.spinner("Scraping Reddit posts…"):
        posts = scrape_subreddit(
            subreddit_url=subreddit_url,
            keywords=keywords,
            max_posts=max_posts,
            scrolls=scrolls,
            headless=headless,
            min_posts=min_posts,
        )

        # 1) write CSV + JSONs to the paths you asked for
        csv_path  = DEFAULT_SETTINGS["csv_path"]
        data_dir  = DEFAULT_SETTINGS["json_basedir"]
        save_outputs(posts, csv_path=csv_path, json_basedir=data_dir)

        # 2) show dataframe
        df = pd.read_csv(csv_path)
        st.header("Scraped Data")
        st.dataframe(df, use_container_width=True)

        # 3) create a zip archive of the data folder
        zip_path = "data.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(data_dir):
                for f in files:
                    abs_f = os.path.join(root, f)
                    rel_f = os.path.relpath(abs_f, data_dir)
                    zf.write(abs_f, rel_f)

        # 4) download buttons
        col1, col2 = st.columns(2)
        with col1:
            with open(csv_path, "rb") as f:
                st.download_button("Download CSV", f, file_name="reddit_posts.csv", mime="text/csv")
        with col2:
            with open(zip_path, "rb") as f:
                st.download_button("Download data.zip", f, file_name="data.zip", mime="application/zip")

    # ───── cleanup local files after buttons are on screen ────────────
    try:
        os.remove(csv_path)
        shutil.rmtree(data_dir, ignore_errors=True)
        os.remove(zip_path)
    except FileNotFoundError:
        pass

    # keep the app alive / auto-refresh
    time.sleep(5)
    st.rerun()
