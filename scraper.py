import json
import os
import time
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

from playwright.sync_api import sync_playwright
from parsel import Selector
from nested_lookup import nested_lookup
import jmespath


def parse_thread(data):
    result = jmespath.search("""{
        text: post.caption.text,
        published_on: post.taken_at,
        code: post.code,
        username: post.user.username,
        like_count: post.like_count
    }""", data)
    if result.get("code") and result.get("username"):
        result["url"] = f"https://www.threads.net/@{result['username']}/post/{result['code']}"
    else:
        result["url"] = ""
    return result


def scrape_profile(username):
    url = f"https://www.threads.net/@{username}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(url, timeout=30000)
        try:
            page.wait_for_selector("[data-pressable-container=true]", timeout=15000)
        except:
            pass
        time.sleep(3)

        # 스크롤을 여러 번 해서 더 많은 글 로딩
        for i in range(5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

        content = page.content()
        browser.close()

    selector = Selector(text=content)
    hidden_datasets = selector.css(
        'script[type="application/json"][data-sjs]::text'
    ).getall()

    threads = []
    seen_codes = set()
    for hidden_dataset in hidden_datasets:
        if '"ScheduledServerJS"' not in hidden_dataset:
            continue
        if "thread_items" not in hidden_dataset:
            continue
        data = json.loads(hidden_dataset)
        thread_items = nested_lookup("thread_items", data)
        for thread in thread_items:
            for t in thread:
                parsed = parse_thread(t)
                if parsed.get("text") and parsed.get("code") not in seen_codes:
                    seen_codes.add(parsed.get("code"))
                    threads.append(parsed)
    return threads


def generate_rss(username, posts):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = f"@{username} - Threads"
    SubElement(channel, "link").text = f"https://www.threads.net/@{username}"
    SubElement(channel, "description").text = f"Threads posts from @{username}"
    SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for post in posts:
        item = SubElement(channel, "item")
        title_text = (post.get("text") or "")[:80]
        if len(post.get("text", "")) > 80:
            title_text += "..."
        SubElement(item, "title").text = title_text
        SubElement(item, "link").text = post.get("url", "")
        SubElement(item, "description").text = post.get("text", "")
        if post.get("published_on"):
            pub_date = datetime.fromtimestamp(
                post["published_on"], tz=timezone.utc
            ).strftime("%a, %d %b %Y %H:%M:%S +0000")
            SubElement(item, "pubDate").text = pub_date
        SubElement(item, "guid").text = post.get("url", "")

    return tostring(rss, encoding="unicode", xml_declaration=True)


def main():
    accounts = [
        "choi.openai",
    ]

    os.makedirs("feeds", exist_ok=True)

    for username in accounts:
        print(f"Scraping @{username}...")
        try:
            posts = scrape_profile(username)
            print(f"  Found {len(posts)} posts")
            rss_xml = generate_rss(username, posts)

            filename = f"feeds/{username.replace('.', '-')}.xml"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(rss_xml)
            print(f"  Saved to {filename}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
