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
        "国家政策简报": [
            "site:gov.cn 国务院 政策 when:2d",
            "site:gov.cn 部委 政策 通知 when:2d",
            "site:news.cn 中国 政策 发布 when:2d",
        ],
        "国家重大经济政策速览": [
            "site:pbc.gov.cn OR site:mof.gov.cn OR site:ndrc.gov.cn 政策 when:2d",
            "site:gov.cn 经济 政策 发布 when:2d",
            "site:news.cn 中国 经济 政策 when:2d",
        ],
        "国际重大新闻速览": [
            "site:news.cn 国际 重大 新闻 when:2d",
            "site:people.com.cn 国际 突发 when:2d",
            "site:cctv.com 国际 要闻 when:2d",
        ],
    },
    "非中文信源版": {
        "国家政策简报": [
            "site:reuters.com China government policy when:2d",
            "site:ft.com China policy when:2d",
            "site:wsj.com China policy when:2d",
        ],
        "国家重大经济政策速览": [
            "site:reuters.com China PBOC fiscal policy when:2d",
            "site:ft.com China economy policy when:2d",
            "site:wsj.com China economy policy when:2d",
        ],
        "国际重大新闻速览": [
            "site:reuters.com world breaking news when:2d",
            "site:apnews.com world breaking news when:2d",
            "site:bbc.com/news world news when:2d",
            "site:ft.com world news when:2d",
        ],
    },
}

# 只保留可追溯的一手机构或长期编辑部媒体。若当日条目不足，页面留空，
# 不用地方公示、内容农场或二次转载补足数量。
TRUSTED_SOURCES = {
    "中文信源版": (
        "中国政府网", "国务院", "新华网", "新华社", "人民日报", "人民网", "央视网",
        "中国人民银行", "财政部", "国家发展和改革委员会", "商务部", "证监会",
        "国家统计局", "海关总署", "中国新闻网",
    ),
    "非中文信源版": (
        "Reuters", "Associated Press", "AP News", "Financial Times", "The Wall Street Journal",
        "Bloomberg", "BBC", "The New York Times", "The Washington Post",
    ),
}

SOURCE_PRIORITY = {
    "中国政府网": 100, "国务院": 100, "中国人民银行": 100, "财政部": 100,
    "国家发展和改革委员会": 100, "商务部": 100, "证监会": 100, "国家统计局": 100,
    "海关总署": 100, "新华网": 90, "新华社": 90, "人民日报": 85, "人民网": 85,
    "央视网": 85, "Reuters": 100, "Associated Press": 95, "AP News": 95,
    "Financial Times": 90, "The Wall Street Journal": 90, "Bloomberg": 90,
    "BBC": 85, "The New York Times": 85, "The Washington Post": 85,
}

SECTION_KEYWORDS = {
    "国家政策简报": ("国务院", "政策", "通知", "决定", "条例", "办法", "regulation", "policy", "state council"),
    "国家重大经济政策速览": ("央行", "财政", "发改", "货币", "金融", "税", "经济", "pbo c", "pboc", "fiscal", "monetary", "economy"),
    "国际重大新闻速览": ("战争", "冲突", "制裁", "选举", "峰会", "贸易", "市场", "world", "war", "conflict", "sanction", "election", "summit", "trade"),
}

# 通过来源白名单后，仍须命中模块主题。这样 Reuters 的第三国政策消息，
# 或新华社的地方民生报道，都不会被放进国家级栏目。
REQUIRED_TITLE_TERMS = {
    "中文信源版": {
        "国家政策简报": ("国务院", "中央", "全国", "国家", "网信办", "药监局", "部", "委"),
        "国家重大经济政策速览": ("国务院", "财政部", "央行", "人民银行", "发改委", "国家", "全国", "货币", "金融", "税"),
        "国际重大新闻速览": ("国际", "全球", "美国", "俄罗斯", "乌克兰", "伊朗", "以色列", "欧洲", "联合国", "中东", "北约", "关税", "贸易"),
    },
    "非中文信源版": {
        "国家政策简报": ("china", "chinese", "beijing", "state council"),
        "国家重大经济政策速览": ("china", "chinese", "beijing", "pboc", "yuan"),
        "国际重大新闻速览": ("world", "global", "iran", "israel", "ukraine", "russia", "europe", "trump", "war", "conflict", "sanction", "tariff", "trade"),
    },
}

LOCAL_ONLY_TERMS = ("福州", "武汉", "重庆", "湖南", "广西", "江苏", "海南", "青岛", "潍坊", "张江", "经开区", "旅行社", "招生", "电梯")


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


def approved(item: dict[str, str], version: str) -> bool:
    source = item["source"].casefold()
    return any(name.casefold() in source for name in TRUSTED_SOURCES[version])


def relevant(item: dict[str, str], version: str, section_name: str) -> bool:
    title = item["title"].casefold()
    if version == "中文信源版" and any(term.casefold() in title for term in LOCAL_ONLY_TERMS):
        return False
    return any(term.casefold() in title for term in REQUIRED_TITLE_TERMS[version][section_name])


def score(item: dict[str, str], section_name: str) -> tuple[int, str]:
    source_score = max((weight for name, weight in SOURCE_PRIORITY.items() if name.casefold() in item["source"].casefold()), default=0)
    title = item["title"].casefold()
    relevance = sum(word.casefold() in title for word in SECTION_KEYWORDS[section_name])
    return (source_score + relevance * 5, item["published"])


def dedupe(items: list[dict[str, str]], version: str, section_name: str, limit: int = 6) -> list[dict[str, str]]:
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    eligible = (item for item in items if approved(item, version) and relevant(item, version, section_name))
    for item in sorted(eligible, key=lambda item: score(item, section_name), reverse=True):
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
        return f"<section><h3>{html.escape(name)}</h3><p class=\"empty\">过去 48 小时内，指定权威信源未检索到足够条目。</p></section>"
    primary = "".join(card(item) for item in items[:3])
    more = "".join(f'<li><a href="{html.escape(item["link"], quote=True)}" target="_blank" rel="noopener">{html.escape(item["title"])}</a></li>' for item in items[3:])
    more_block = f"<details><summary>更多新闻</summary><ul>{more}</ul></details>" if more else ""
    return f"<section><h3>{html.escape(name)}</h3>{primary}{more_block}</section>"


def build() -> None:
    versions: list[str] = []
    for version, sections in QUERIES.items():
        rendered = []
        for name, queries in sections.items():
            candidates: list[dict[str, str]] = []
            for query in queries:
                candidates.extend(fetch_items(query, version == "中文信源版"))
            items = dedupe(candidates, version, name)
            rendered.append(section(name, items))
        versions.append(f'<div class="version"><h2>{html.escape(version)}</h2>{"".join(rendered)}</div>')
    local_now = NOW.astimezone(dt.timezone(dt.timedelta(hours=8)))
    OUTPUT.write_text(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>每日新闻情报</title><style>body{{margin:0;background:#f5f4ef;color:#18212d;font:16px system-ui,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:980px;margin:auto;padding:44px 20px}}h1{{font-size:34px;margin:0 0 8px}}.meta{{color:#617083;margin:0 0 28px}}.version{{background:#fff;border:1px solid #e4e2da;border-radius:18px;padding:24px;margin:20px 0}}h2{{font-size:24px;margin:0 0 18px;color:#0a5a50}}section{{border-top:1px solid #eee;padding:18px 0}}section:first-of-type{{border-top:0;padding-top:0}}h3{{font-size:18px;margin:0 0 12px}}article{{padding:12px 0;border-top:1px dashed #ddd}}article:first-of-type{{border-top:0}}a{{color:#075ec6;text-decoration:none;font-weight:650;line-height:1.45}}a:hover{{text-decoration:underline}}article p,.empty{{color:#697586;font-size:13px;margin:6px 0 0}}details{{margin-top:14px}}summary{{cursor:pointer;color:#38556e}}li{{margin:9px 0}}footer{{color:#728092;font-size:13px;margin:28px 0 0}}</style></head><body><main><h1>每日新闻情报</h1><p class="meta">最近 48 小时内新闻 · 自动更新于北京时间 {local_now:%Y-%m-%d %H:%M}</p>{"".join(versions)}<footer>本页由自动化任务每日生成。链接指向原始新闻页面，请以原始来源为准。</footer></main></body></html>''', encoding="utf-8")


if __name__ == "__main__":
    build()
