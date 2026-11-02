from __future__ import annotations
import hashlib, json, re, sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import feedparser, requests, yaml
CATEGORIES = ("news", "analysis", "research", "niche")
HEADERS = {"User-Agent": "GlobalFinanceIntelligence/0.1 (public research collector; contact: repo owner)"}
def clean_url(url):
    p=urlsplit(url or "")
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),"", ""))
def load_sources(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["sources"]
def collect(sources, timeout=15):
    rows=[]
    for s in sources:
        try:
            r=requests.get(s["url"],headers=HEADERS,timeout=timeout); r.raise_for_status()
            parsed=feedparser.parse(r.content)
            for e in parsed.entries:
                link=clean_url(e.get("link"))
                title=re.sub(r"\s+"," ",e.get("title","")).strip()
                if not title or not link: continue
                published=e.get("published",e.get("updated", ""))
                summary=re.sub(r"<[^>]+>"," ",e.get("summary", ""))[:700]
                key=hashlib.sha256((link or title).encode()).hexdigest()
                rows.append({"id":key,"title":title,"url":link,"published":published,"summary":summary,"source":s["name"],"category":s["category"],"tier":s.get("tier","unknown"),"collected_at":datetime.now(timezone.utc).isoformat()})
        except Exception as ex:
            print(f"source unavailable: {s['name']}: {ex}")
    return dedupe(rows)
def dedupe(rows):
    out={}
    for x in rows: out.setdefault(x["id"],x)
    return list(out.values())
def viewpoint(item):
    text=re.sub(r"\s+"," ",(item.get("title","")+". "+item.get("summary",""))).strip()
    positive=("rise","gain","growth","upgrade","beat","rally","easing","cut rates","surge")
    negative=("fall","drop","decline","downgrade","miss","recession","tariff","inflation","selloff")
    low=text.lower()
    pos=any(re.search(r"\b"+re.escape(w)+r"\b",low) for w in positive)
    neg=any(re.search(r"\b"+re.escape(w)+r"\b",low) for w in negative)
    label="混合" if pos and neg else "利多" if pos else "利空" if neg else "中性"
    return label, text[:240] or "无可引用摘要"
def event_key(item):
    words=re.findall(r"[a-z0-9]+",item.get("title","").lower())
    stop={"the","a","an","and","or","of","to","in","on","for","with","as","at","from","after","by"}
    return " ".join(sorted(set(w for w in words if w not in stop))[:8]) or item["id"]
def published_at(item):
    raw=item.get("published","")
    try: return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except (ValueError, TypeError, IndexError):
        try: return datetime.fromisoformat(raw.replace("Z","+00:00")).astimezone(timezone.utc)
        except (ValueError, TypeError): return None
def score(item):
    # Transparent heuristic; no paid model or unsupported sentiment inference.
    text=(item["title"]+" "+item.get("summary","")).lower()
    terms=("fed","rate","inflation","earnings","tariff","bond","oil","bank","credit","recession","market")
    return min(100, 20 + 8*sum(t in text for t in terms) + (15 if item.get("tier")=="primary" else 0))
def save_db(path, items):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,title TEXT,url TEXT,published TEXT,summary TEXT,source TEXT,category TEXT,tier TEXT,collected_at TEXT,score INTEGER)")
        db.executemany("INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?,?,?)",[(x["id"],x["title"],x["url"],x["published"],x["summary"],x["source"],x["category"],x["tier"],x["collected_at"],score(x)) for x in items])
def render(items, day):
    out=[f"# 全球金融情报日报 | {day}","","> 基于可公开访问来源自动整理。摘要为来源标题/短摘要，非投资建议。观点归纳仅反映原文表述，不代表事实判断。",""]
    labels={"news":"新闻","analysis":"解读","research":"公开研究","niche":"长尾观点","discovery":"待核验发现"}
    cutoff=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)-timedelta(days=2)
    fresh=[x for x in items if published_at(x) and published_at(x)>=cutoff]
    out += [f"本期近 72 小时可核验条目：{len(fresh)}；采集总数：{len(items)}。",""]
    for cat in (*CATEGORIES,"discovery"):
        group=sorted((x for x in fresh if x["category"]==cat),key=lambda x:(score(x),published_at(x)),reverse=True)[:8]
        out += [f"## {labels[cat]}"]
        if not group: out.append("- 今日暂无可用条目。")
        for x in group:
            desc=(x.get("summary","").strip() or "暂无公开摘要").replace("\n"," ")
            stance,evidence=viewpoint(x)
            out.append(f"- **{x['title']}** — {x['source']} · {x.get('published','')} · 评分 {score(x)} · {stance}  \n  摘要：{desc[:350]}  \n  观点依据（原文标题/摘要）：{evidence}  \n  [原文]({x['url']})")
        out.append("")
    out += ["## 方法与局限","采集基于公开 RSS；源可用性会变化，缺少 RSS 的研报不会被系统覆盖。未绕过登录或付费墙，也不下载全文。观点方向仅按标题和摘要关键词判断，可能误判；小道消息仅作为待核验发现，须回到原文确认。"]
    return "\n".join(out)+"\n"
def run(root=Path(".")):
    sources=load_sources(root/"sources/sources.yaml"); items=collect(sources)
    save_db(root/"data/history.sqlite3",items)
    (root/"data/latest.json").write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
    day=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    (root/f"reports/{day}.md").parent.mkdir(exist_ok=True)
    (root/f"reports/{day}.md").write_text(render(items,day),encoding="utf-8")
    return len(items)
