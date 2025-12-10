#!/usr/bin/env python3

import argparse
import csv
import json
import random
import time
import logging
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

SOURCES = {
    "bbc": {
        "url": "https://www.bbc.com/news",
        "base": "https://www.bbc.com",
        "article_selector": "a.gs-c-promo-heading",
        "title_selector": None,
        "url_attr": "href",
        "time_selector": "time",
    },
    "guardian": {
        "url": "https://www.theguardian.com/international",
        "base": "https://www.theguardian.com",
        "article_selector": "a.js-headline-text",
        "title_selector": None,
        "url_attr": "href",
        "time_selector": "time",
    },
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def is_allowed_by_robots(url, user_agent="*"):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = base + "/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except:
        return True

def fetch_url(url, headers=None, timeout=10, max_retries=3, backoff_factor=1.0):
    headers = headers or {"User-Agent": "headline-scraper/1.0"}
    attempt = 0
    while attempt < max_retries:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except:
            attempt += 1
            sleep_for = backoff_factor * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            time.sleep(sleep_for)
    raise RuntimeError(f"Failed to fetch {url}")

def parse_headlines_from_soup(soup, cfg):
    items = []
    nodes = soup.select(cfg["article_selector"])
    for node in nodes:
        try:
            if cfg.get("title_selector"):
                t = node.select_one(cfg["title_selector"])
                title = t.get_text(strip=True) if t else node.get_text(strip=True)
            else:
                title = node.get_text(strip=True)

            href = node.get(cfg.get("url_attr", "href")) or (node.find("a") and node.find("a").get("href"))
            if not href:
                continue
            url = urljoin(cfg.get("base", ""), href)

            time_text = None
            if cfg.get("time_selector"):
                time_el = node.select_one(cfg["time_selector"]) or node.find(cfg["time_selector"])
                if time_el:
                    time_text = time_el.get("datetime") or time_el.get_text(strip=True)
                    try:
                        time_text = dateparser.parse(time_text, fuzzy=True).isoformat()
                    except:
                        pass

            items.append({"title": title, "url": url, "time": time_text})
        except:
            pass
    return items

def generic_parse(soup, base):
    selectors = [
        ("article h1 a", "href"),
        ("article h2 a", "href"),
        ("h3 a", "href"),
        ("a[href] > h3", "href"),
        ("a[href].headline", "href"),
    ]
    found = []
    for sel, attr in selectors:
        nodes = soup.select(sel)
        for n in nodes:
            title = n.get_text(strip=True)
            href = n.get(attr) or (n.parent and n.parent.get(attr))
            if href:
                found.append({"title": title, "url": urljoin(base, href), "time": None})
    return found

def save_results(items, output_path, fmt="json"):
    if fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        keys = ["title", "url", "time", "source"]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for it in items:
                writer.writerow({k: it.get(k) for k in keys})

def scrape_sources(sources_to_scrape, keyword=None, delay=2.0, jitter=1.0, user_agent="headline-scraper/1.0"):
    results = []
    for src_key in sources_to_scrape:
        cfg = SOURCES.get(src_key)
        if not cfg:
            continue
        start_url = cfg["url"]

        if not is_allowed_by_robots(start_url, user_agent=user_agent):
            continue

        time.sleep(delay + random.uniform(0, jitter))

        try:
            resp = fetch_url(start_url, headers={"User-Agent": user_agent})
            soup = BeautifulSoup(resp.text, "html.parser")
            items = parse_headlines_from_soup(soup, cfg)
            if not items:
                items = generic_parse(soup, cfg.get("base", ""))

            seen = set()
            filtered = []
            for it in items:
                if keyword:
                    if keyword.lower() not in (it.get("title") or "").lower():
                        continue
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                it["source"] = src_key
                filtered.append(it)
            results.extend(filtered)
        except:
            pass
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", "-s", type=str, default=",".join(SOURCES.keys()))
    parser.add_argument("--format", "-f", choices=["json", "csv"], default="json")
    parser.add_argument("--output", "-o", type=str, default="headlines.json")
    parser.add_argument("--keyword", "-k", type=str, default=None)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--jitter", type=float, default=1.0)
    parser.add_argument("--user-agent", type=str, default="headline-scraper/1.0")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    items = scrape_sources(sources, keyword=args.keyword, delay=args.delay, jitter=args.jitter, user_agent=args.user_agent)

    unique = []
    seen = set()
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            unique.append(it)

    save_results(unique, args.output, args.format)

if __name__ == "__main__":
    main()
