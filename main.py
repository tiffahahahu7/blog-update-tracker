import os
import feedparser
import requests
from bs4 import BeautifulSoup
from notion_client import Client
from datetime import datetime

notion = Client(auth=os.getenv("NOTION_TOKEN"))
database_id = os.getenv("NOTION_DB_ID")

def fetch_rows():
    results = []
    has_more = True
    start_cursor = None

    while has_more:
        response = notion.databases.query(
            database_id=database_id,
            start_cursor=start_cursor
        )
        results.extend(response["results"])
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    return results

def update_page(page_id, title, url):
    notion.pages.update(
        page_id=page_id,
        properties={
            "Status": {"select": {"name": "Updated"}},
            "Last Title": {"rich_text": [{"text": {"content": title}}]},
            "Last URL": {"url": url},
            "Last Updated": {"date": {"start": datetime.utcnow().isoformat()}}
        }
    )

def check_rss(rss_url):
    parsed = feedparser.parse(rss_url)
    if parsed.entries:
        entry = parsed.entries[0]
        return entry.title, entry.link
    return None, None

def check_html(url, selector):
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        element = soup.select_one(selector)
        if element:
            return element.text.strip(), requests.compat.urljoin(url, element.get("href"))
    except Exception as e:
        print(f"HTML check failed: {e}")
    return None, None

def get_prop(props, key, subkey="text"):
    value = props.get(key)
    if not value:
        return ""
    if value.get("type") == "rich_text":
        texts = value.get("rich_text", [])
        return texts[0]["text"].get(subkey) if texts else ""
    elif value.get("type") == "select":
        return value["select"]["name"] if value["select"] else ""
    elif value.get("type") == "url":
        return value["url"]
    return ""

def run():
    rows = fetch_rows()
    for row in rows:
        props = row["properties"]
        page_id = row["id"]
        status = get_prop(props, "Status")

        if status.lower().strip() != "default":
            continue

        rss_url = get_prop(props, "RSS URL")
        selector = get_prop(props, "Selector")
        link = get_prop(props, "Link", subkey="url")
        last_title = get_prop(props, "Last Title")

        if rss_url:
            title, url = check_rss(rss_url)
        elif link and selector:
            title, url = check_html(link, selector)
        else:
            continue

        if title and title != last_title:
            print(f"[UPDATED] {get_prop(props, 'Name')} → {title}")
            update_page(page_id, title, url)

if __name__ == "__main__":
    run()
