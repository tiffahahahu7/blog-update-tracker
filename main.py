import os
import feedparser
import requests
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime

notion = Client(auth=os.getenv("NOTION_TOKEN"))
database_id = os.getenv("NOTION_DB_ID")

def fetch_blog_entries():
    query = notion.databases.query(database_id=database_id)
    return query["results"]

def update_notion_page(page_id, title, link):
    notion.pages.update(
        page_id=page_id,
        properties={
            "Status": {"select": {"name": "updated"}},
            "Last Title": {"rich_text": [{"text": {"content": title}}]},
            "Last Link": {"url": link},
            "Last Updated": {"date": {"start": datetime.utcnow().isoformat()}}
        }
    )

def check_rss(feed_url):
    d = feedparser.parse(feed_url)
    if d.entries:
        entry = d.entries[0]
        return entry.title, entry.link
    return None, None

def check_html(url, selector):
    res = requests.get(url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    post = soup.select_one(selector)
    if post:
        return post.text.strip(), requests.compat.urljoin(url, post.get("href"))
    return None, None

def run():
    for row in fetch_blog_entries():
        props = row["properties"]
        page_id = row["id"]
        status = props["Status"]["select"]["name"]
        if status != "default":
            continue

        rss_url = props.get("RSS Feed", {}).get("url")
        blog_url = props.get("Blog URL", {}).get("url")
        selector = props.get("Selector", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
        last_title = props.get("Last Title", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")

        title, link = (check_rss(rss_url) if rss_url else check_html(blog_url, selector))

        if title and title != last_title:
            update_notion_page(page_id, title, link)

if __name__ == "__main__":
    run()
