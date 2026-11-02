from __future__ import annotations
import hashlib, json, re, sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import feedparser, requests, yaml
CATEGORIES = ("news", "analysis", "research", "niche")
ASSETS = {
    "美股": ("s&p 500","nasdaq","dow jones","us equities","u.s. stocks","wall street","stock market"),
    "科技": ("artificial intelligence"," ai ","semiconductor","chip","nvidia","microsoft","apple","alphabet","amazon","meta","data center"),
    "美债": ("treasury","bond yield","interest rate","fomc","federal reserve","fed rate","inflation","consumer price index","employment situation"),
    "美元": ("dollar","foreign exchange","fed rate","fomc","federal reserve","inflation","consumer price index","employment situation"),
    "欧洲市场": ("europe","eurozone","euro area","ecb","european central bank","eu economy"),
    "黄金": ("gold","precious metal","real yield","safe haven"),
    "原油": ("crude oil","oil price","petroleum","opec","eia","energy information administration"),
}
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
def asset_tags(item):
    text=" "+(item.get("title","")+" "+item.get("summary","")).lower()+" "
    return [asset for asset, terms in ASSETS.items() if any(t in text for t in terms)]
def market_relevance(item):
    title=item.get("title","").lower()
    if any(x in title for x in ("price target","consensus price target","key takeaways for long-term investors")):
        return 0
    tags=asset_tags(item)
    if not tags: return 0
    return score(item)+10*len(tags)+(20 if item.get("tier")=="primary" else 0)
def save_db(path, items):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,title TEXT,url TEXT,published TEXT,summary TEXT,source TEXT,category TEXT,tier TEXT,collected_at TEXT,score INTEGER)")
        db.executemany("INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?,?,?)",[(x["id"],x["title"],x["url"],x["published"],x["summary"],x["source"],x["category"],x["tier"],x["collected_at"],score(x)) for x in items])
def render(items, day):
    out=[f"# 全球金融情报日报 | {day}","","> 按资产筛选的公开来源索引。方向需结合原文和行情核验；标题关键词不能单独推断利好利空。",""]
    cutoff=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)-timedelta(days=2)
    fresh=[x for x in items if published_at(x) and published_at(x)>=cutoff and market_relevance(x)>0]
    out += [f"近 72 小时采集 {len(items)} 条；通过主要资产相关性筛选 {len(fresh)} 条。",""]
    for asset in ASSETS:
        group=sorted((x for x in fresh if asset in asset_tags(x)),key=lambda x:(market_relevance(x),published_at(x)),reverse=True)[:5]
        out += [f"## {asset}"]
        if not group: out.append("- 暂无足够重要且可核验的事件。")
        for x in group:
            desc=(x.get("summary","").strip() or "暂无公开摘要").replace("\n"," ")
            out.append(f"- **{x['title']}** — {x['source']} · {x.get('published','')} · 相关性 {market_relevance(x)}  \n  原始摘要：{desc[:350]}  \n  影响方向：待核对原文、市场预期与最新行情。  \n  [原文]({x['url']})")
        out.append("")
    out += ["## 方法与局限","此文件是机器筛选索引；中文解读和利好利空判断需在定时对话中结合原文与市场数据完成。单一资产可以出现在多个栏目。来源缺口保留为空，不用零散公司新闻填充。"]
    return "\n".join(out)+"\n"
def run(root=Path(".")):
    sources=load_sources(root/"sources/sources.yaml"); items=collect(sources)
    save_db(root/"data/history.sqlite3",items)
    (root/"data/latest.json").write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
    day=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    (root/f"reports/{day}.md").parent.mkdir(exist_ok=True)
    (root/f"reports/{day}.md").write_text(render(items,day),encoding="utf-8")
    return len(items)
