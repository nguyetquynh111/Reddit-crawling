import streamlit as st
import pandas as pd
import pathlib, os, shutil, time, zipfile
from test import scrape_subreddit, save_outputs

# ───── Safe playwright install ────────────────────────────────────────
def ensure_playwright_installed():
    if not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
        with st.spinner("Installing Playwright browsers (first time only)…"):
            os.system("playwright install")

ensure_playwright_installed()

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
    "zip_path":      "data.zip",
}

st.title("Reddit Scraper")

# ───── Setup Session State ────────────────────────────────────────────
if "scraped_df" not in st.session_state:
    st.session_state.scraped_df = None
if "csv_path" not in st.session_state:
    st.session_state.csv_path = DEFAULT_SETTINGS["csv_path"]
if "zip_path" not in st.session_state:
    st.session_state.zip_path = DEFAULT_SETTINGS["zip_path"]
if "data_dir" not in st.session_state:
    st.session_state.data_dir = DEFAULT_SETTINGS["json_basedir"]

# ───── sidebar inputs ─────────────────────────────────────────────────
st.sidebar.header("Scraping Settings")
subreddit_url = st.sidebar.text_input("Subreddit URL", value=DEFAULT_SETTINGS["subreddit_url"])
keywords_str  = st.sidebar.text_input("Keywords (comma-separated)", ", ".join(DEFAULT_SETTINGS["keywords"]))
max_posts     = st.sidebar.number_input("Maximum Posts", 1, value=DEFAULT_SETTINGS["max_posts"])
scrolls       = st.sidebar.number_input("Number of Scrolls", 1, value=DEFAULT_SETTINGS["scrolls"])
min_posts     = st.sidebar.number_input("Minimum Posts", 1, value=DEFAULT_SETTINGS["min_posts"])
headless      = st.sidebar.checkbox("Headless Mode", value=DEFAULT_SETTINGS["headless"])
username = st.sidebar.text_input("Reddit username")
password = st.sidebar.text_input("Reddit password")
keywords      = [k.strip() for k in keywords_str.split(",") if k.strip()]

# ───── scraping ───────────────────────────────────────────────────────
if st.sidebar.button("Start Scraping"):
    with st.spinner("Scraping Reddit posts…"):
        posts = scrape_subreddit(
            username=username,
            password=password,
            subreddit_url=subreddit_url,
            keywords=keywords,
            max_posts=max_posts,
            scrolls=scrolls,
            headless=headless,
            min_posts=min_posts,
        )

        if not posts:
            st.warning("No posts found. Try adjusting keywords or subreddit settings.")
            st.stop()

        # Save outputs
        csv_path = DEFAULT_SETTINGS["csv_path"]
        data_dir = DEFAULT_SETTINGS["json_basedir"]
        save_outputs(posts, csv_path=csv_path, json_basedir=data_dir)

        # Read into dataframe
        df = pd.read_csv(csv_path)
        st.session_state.scraped_df = df

        # Save paths
        st.session_state.csv_path = csv_path
        st.session_state.data_dir = data_dir

        # Create zip
        zip_path = DEFAULT_SETTINGS["zip_path"]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(data_dir):
                for f in files:
                    abs_f = os.path.join(root, f)
                    rel_f = os.path.relpath(abs_f, data_dir)
                    zf.write(abs_f, rel_f)
        st.session_state.zip_path = zip_path

        st.success("Scraping done! Scroll down to see the results.")

# ───── displaying data and downloads ──────────────────────────────────
if st.session_state.scraped_df is not None:
    st.header("Scraped Data")
    st.dataframe(st.session_state.scraped_df, use_container_width=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        with open(st.session_state.csv_path, "rb") as f:
            st.download_button(
                "Download CSV",
                f,
                file_name="reddit_posts.csv",
                mime="text/csv",
            )

    with col2:
        with open(st.session_state.zip_path, "rb") as f:
            st.download_button(
                "Download data.zip",
                f,
                file_name="data.zip",
                mime="application/zip",
            )

    with col3:
        if st.button("🗑️ Delete files", type="primary"):
            try:
                os.remove(st.session_state.csv_path)
                shutil.rmtree(st.session_state.data_dir, ignore_errors=True)
                os.remove(st.session_state.zip_path)
                st.session_state.scraped_df = None
                st.success("Temporary files removed.")
                time.sleep(2)
                st.rerun()
            except FileNotFoundError:
                st.info("Files already deleted or not found.")

