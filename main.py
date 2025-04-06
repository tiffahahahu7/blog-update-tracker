import os
import feedparser
import requests
from bs4 import BeautifulSoup
from notion_client import Client
from urllib.parse import urlparse

def normalize_url(url):
    if not urlparse(url).scheme:
        return "https://" + url
    return url

# Set up Notion client
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
            "Status": {"status": {"name": "Updated"}},
            "Last Title": {"rich_text": [{"text": {"content": title}}]},
            "Last URL": {"url": url},
        }
    )


def mark_page_as_error(page_id):
    notion.pages.update(
        page_id=page_id,
        properties={
            "Status": {"status": {"name": "Error"}}
        }
    )


def check_rss(rss_url):
    try:
        rss_url = normalize_url(rss_url)

        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'

        parsed = feedparser.parse(response.text)

        if parsed.bozo and hasattr(parsed, "bozo_exception"):
            raise Exception(parsed.bozo_exception)

        if parsed.entries:
            entry = parsed.entries[0]
            return entry.title, entry.link

    except Exception as e:
        print(f"❌ RSS check failed: {e}")
        raise e

    return None, None


def check_html(url, selector):
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        element = soup.select_one(selector)
        if element:
            return element.text.strip(), requests.compat.urljoin(url, element.get("href"))
    except Exception as e:
        print(f"❌ HTML check failed: {e}")
        raise e
    return None, None


def get_prop(props, key, subkey="content"):
    value = props.get(key)
    if not value:
        return ""

    prop_type = value.get("type")

    if prop_type == "title":
        texts = value.get("title", [])
        return texts[0]["text"].get(subkey) if texts else ""

    elif prop_type == "rich_text":
        texts = value.get("rich_text", [])
        return texts[0]["text"].get(subkey) if texts else ""

    elif prop_type in ["select", "status"]:
        return value[prop_type]["name"] if value[prop_type] else ""

    elif prop_type == "url":
        return value["url"]

    return ""

def run():
    print("🟢 Starting blog tracker...")
    rows = fetch_rows()
    print(f"🔍 Fetched {len(rows)} rows from Notion")

    for row in rows:
        props = row["properties"]
        page_id = row["id"]

        name = get_prop(props, "Name")
        status = get_prop(props, "Status")
        rss_url = get_prop(props, "RSS URL")
        selector = get_prop(props, "Selector")
        link = get_prop(props, "Link", subkey="url")
        last_title = (get_prop(props, "Last Title") or "").strip()
        last_url = (get_prop(props, "Last URL", subkey="url") or "").strip()

        if status.lower().strip() != "default":
            continue

        print(f"\n📄 Checking blog: {name}")
        title, url = None, None

        try:
            if rss_url:
                title, url = check_rss(rss_url)
            elif link and selector:
                title, url = check_html(link, selector)
            else:
                mark_page_as_error(page_id)
                print("⚠️ No valid RSS or selector. Skipping.")
                continue
        except Exception:
            mark_page_as_error(page_id)
            print(f"🚨 Marking {name} as Error due to access failure.")
            continue

        if not title or not url:
            print(f"⚠️ Could not extract article from {name}. Marking as Error.")
            mark_page_as_error(page_id)
            continue

        if (url and url.strip() != last_url) or (title and title.strip() != last_title):
            print(f"✅ New update found! Updating Notion entry...")
            update_page(page_id, title, url)
        else:
            print(f"📭 No update detected.")

    print("\n✅ Script completed.")


if __name__ == "__main__":
    run()
