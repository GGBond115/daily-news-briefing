from __future__ import annotations

import datetime as dt
import email.utils
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).parent
OUTPUT = ROOT / "index.html"
NOW = dt.datetime.now(dt.timezone.utc)
WINDOW = NOW - dt.timedelta(hours=48)

QUERIES = {
    "中文信源版": {
        "国家政策简报": "国务院 部委 最新 政策 OR 通知",
        "国家重大经济政策速览": "中国 央行 财政部 发改委 经济 政策",
        "国际重大新闻速览": "国际 重大 新闻 地缘政治 经济",
    },
    "非中文信源版": {
        "国家政策简报": "China government policy latest",
        "国家重大经济政策速览": "China economic policy PBOC finance latest",
        "国际重大新闻速览": "world breaking news Reuters AP FT WSJ",
    },
}


def rss_url(query: str, chinese: bool) -> str:
    params = {"q": query, "hl": "zh-CN" if chinese else "en-US", "gl": "CN" if chinese else "US", "ceid": "CN:zh-Hans" if chinese else "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def text(node: ET.Element | None, tag: str) -> str:
    child = node.find(tag) if node is not None else None
    return (child.text or "").strip() if child is not None else ""


def parse_date(value: str) -> dt.datetime | None:
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch_items(query: str, chinese: bool) -> list[dict[str, str]]:
    request = urllib.request.Request(rss_url(query, chinese), headers={"User-Agent": "daily-news-briefing/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            root = ET.fromstring(response.read())
    except Exception:
        return []
    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        published = parse_date(text(item, "pubDate"))
        if not published or published < WINDOW:
            continue
        title = text(item, "title")
        link = text(item, "link")
        source = text(item, "source") or "Google News"
        if title and link:
            results.append({"title": title, "link": link, "source": source, "published": published.strftime("%Y-%m-%d %H:%M UTC")})
    return results


def dedupe(items: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for item in items:
        key = item["title"].lower().replace(" ", "")[:80]
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) == limit:
            break
    return output


def card(item: dict[str, str]) -> str:
    title = html.escape(item["title"])
    source = html.escape(item["source"])
    published = html.escape(item["published"])
    return f'<article><a href="{html.escape(item["link"], quote=True)}" target="_blank" rel="noopener">{title}</a><p>{source} · {published}</p></article>'


def section(name: str, items: list[dict[str, str]]) -> str:
    if not items:
        return f"<section><h3>{html.escape(name)}</h3><p class=\"empty\">过去 48 小时内未找到足够的可核验条目。</p></section>"
    primary = "".join(card(item) for item in items[:3])
    more = "".join(f'<li><a href="{html.escape(item["link"], quote=True)}" target="_blank" rel="noopener">{html.escape(item["title"])}</a></li>' for item in items[3:])
    more_block = f"<details><summary>更多新闻</summary><ul>{more}</ul></details>" if more else ""
    return f"<section><h3>{html.escape(name)}</h3>{primary}{more_block}</section>"


def build() -> None:
    versions: list[str] = []
    for version, sections in QUERIES.items():
        rendered = []
        for name, query in sections.items():
            items = dedupe(fetch_items(query, version == "中文信源版"))
            rendered.append(section(name, items))
        versions.append(f'<div class="version"><h2>{html.escape(version)}</h2>{"".join(rendered)}</div>')
    local_now = NOW.astimezone(dt.timezone(dt.timedelta(hours=8)))
    OUTPUT.write_text(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>每日新闻情报</title><style>body{{margin:0;background:#f5f4ef;color:#18212d;font:16px system-ui,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:980px;margin:auto;padding:44px 20px}}h1{{font-size:34px;margin:0 0 8px}}.meta{{color:#617083;margin:0 0 28px}}.version{{background:#fff;border:1px solid #e4e2da;border-radius:18px;padding:24px;margin:20px 0}}h2{{font-size:24px;margin:0 0 18px;color:#0a5a50}}section{{border-top:1px solid #eee;padding:18px 0}}section:first-of-type{{border-top:0;padding-top:0}}h3{{font-size:18px;margin:0 0 12px}}article{{padding:12px 0;border-top:1px dashed #ddd}}article:first-of-type{{border-top:0}}a{{color:#075ec6;text-decoration:none;font-weight:650;line-height:1.45}}a:hover{{text-decoration:underline}}article p,.empty{{color:#697586;font-size:13px;margin:6px 0 0}}details{{margin-top:14px}}summary{{cursor:pointer;color:#38556e}}li{{margin:9px 0}}footer{{color:#728092;font-size:13px;margin:28px 0 0}}</style></head><body><main><h1>每日新闻情报</h1><p class="meta">最近 48 小时内新闻 · 自动更新于北京时间 {local_now:%Y-%m-%d %H:%M}</p>{"".join(versions)}<footer>本页由自动化任务每日生成。链接指向原始新闻页面，请以原始来源为准。</footer></main></body></html>''', encoding="utf-8")


if __name__ == "__main__":
    build()
