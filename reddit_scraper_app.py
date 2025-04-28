import streamlit as st
import pandas as pd
import json
import pathlib
import time
from test import scrape_subreddit, save_outputs

# Default settings
DEFAULT_SETTINGS = {
    "subreddit_url": "https://www.reddit.com/r/webscraping/",
    "keywords": ["OpenAI", "GPT", "Learning"],
    "max_posts": 200,
    "scrolls": 5,
    "min_posts": 100,
    "headless": True,
    "csv_path": "reddit_posts_and_first_comments.csv",
    "json_basedir": pathlib.Path("data")
}

st.set_page_config(page_title="Reddit Scraper", layout="wide")

st.title("Reddit Scraper")

# Sidebar for user settings
st.sidebar.header("Scraping Settings")

# Input fields
subreddit_url = st.sidebar.text_input("Subreddit URL", value=DEFAULT_SETTINGS["subreddit_url"])
keywords_input = st.sidebar.text_input("Keywords (comma-separated)", value=", ".join(DEFAULT_SETTINGS["keywords"]))
max_posts = st.sidebar.number_input("Maximum Posts", min_value=1, value=DEFAULT_SETTINGS["max_posts"])
scrolls = st.sidebar.number_input("Number of Scrolls", min_value=1, value=DEFAULT_SETTINGS["scrolls"])
min_posts = st.sidebar.number_input("Minimum Posts", min_value=1, value=DEFAULT_SETTINGS["min_posts"])
headless = st.sidebar.checkbox("Headless Mode", value=DEFAULT_SETTINGS["headless"])

# Convert keywords string to list
keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

# Scrape button
if st.sidebar.button("Start Scraping"):
    with st.spinner("Scraping Reddit posts..."):
        # Run scraper with parameters
        posts = scrape_subreddit(
            subreddit_url=subreddit_url,
            keywords=keywords,
            max_posts=max_posts,
            scrolls=scrolls,
            headless=headless,
            min_posts=min_posts
        )
        
        # Save outputs with parameters
        save_outputs(
            records=posts,
            csv_path=DEFAULT_SETTINGS["csv_path"],
            json_basedir=DEFAULT_SETTINGS["json_basedir"]
        )
        
        # Read and display CSV
        df = pd.read_csv(DEFAULT_SETTINGS["csv_path"])
        st.header("Scraped Data")
        st.dataframe(df)
        
        # Download buttons
        col1, col2 = st.columns(2)
        
        with col1:
            with open(DEFAULT_SETTINGS["csv_path"], 'rb') as f:
                st.download_button(
                    label="Download CSV",
                    data=f,
                    file_name="reddit_posts.csv",
                    mime="text/csv"
                )
        
        with col2:
            # Create a zip file containing all JSON files
            import shutil
            import tempfile
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                shutil.make_archive(tmp_file.name[:-4], 'zip', DEFAULT_SETTINGS["json_basedir"])
                with open(tmp_file.name, 'rb') as f:
                    st.download_button(
                        label="Download JSON Files",
                        data=f,
                        file_name="reddit_posts_json.zip",
                        mime="application/zip"
                    )

    # Optionally auto-rerun the app to keep it alive after scraping
    time.sleep(5)  # Delay for 5 seconds
    st.rerun()  # This will rerun the app, keeping it live