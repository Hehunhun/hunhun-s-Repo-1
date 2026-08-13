from __future__ import annotations

import json
import re
import traceback
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

OUT = Path("bulk_probe_output")
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})


def probe(name: str, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "url": url, "params": params}
    try:
        r = S.get(url, params=params, timeout=(12, 40), allow_redirects=True)
        r.encoding = r.apparent_encoding or r.encoding
        text = r.text
        (RAW / f"{name}.html").write_text(text[:1_000_000], encoding="utf-8", errors="replace")
        soup = BeautifulSoup(text, "lxml")
        forms = []
        for f in soup.find_all("form"):
            controls = []
            for c in f.find_all(["input", "select", "button"]):
                controls.append({
                    "tag": c.name,
                    "name": c.get("name"),
                    "id": c.get("id"),
                    "value": c.get("value"),
                    "type": c.get("type"),
                    "options": [o.get("value") for o in c.find_all("option")[:20]],
                })
            forms.append({"action": f.get("action"), "method": f.get("method"), "controls": controls})
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if any(k in href.lower() for k in ["history", "sjh", "page", "list", "kaijiang", "open"]):
                links.append({"href": href, "text": label[:100]})
        scripts = []
        for sc in soup.find_all("script"):
            src = sc.get("src")
            body = sc.get_text(" ", strip=True)
            if src or any(k in body.lower() for k in ["ajax", "history", "sjh", "page", "api"]):
                scripts.append({"src": src, "body": body[:5000]})
        item.update({
            "status": r.status_code,
            "final_url": r.url,
            "length": len(r.content),
            "encoding": r.encoding,
            "title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "forms": forms[:20],
            "links": links[:300],
            "scripts": scripts[:100],
            "text_head": re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:3000],
            "table_count": len(soup.find_all("table")),
            "row_count": len(soup.find_all("tr")),
        })
    except Exception as exc:
        item["error"] = repr(exc)
        item["traceback"] = traceback.format_exc()
    return item

CASES = [
    ("8200_fc3d_history", "https://www.8200.cn/kjh/3d/history.htm", None),
    ("8200_fc3d_history_size", "https://www.8200.cn/kjh/3d/history.htm", {"size": 4000}),
    ("8200_fc3d_history_2025", "https://www.8200.cn/kjh/3d/history.htm", {"year": 2025, "size": 4000}),
    ("8200_pl3_history", "https://www.8200.cn/kjh/p3/history.htm", None),
    ("8200_pl3_history_size", "https://www.8200.cn/kjh/p3/history.htm", {"size": 4000}),
    ("8200_pl3_history_2025", "https://www.8200.cn/kjh/p3/history.htm", {"year": 2025, "size": 4000}),
    ("8200_pl5_history", "https://www.8200.cn/kjh/p5/history.htm", None),
    ("8200_pl5_history_size", "https://www.8200.cn/kjh/p5/history.htm", {"size": 4000}),
    ("8200_fc3d_sjh", "https://www.8200.cn/kjh/3d/sjh.htm", None),
    ("8200_fc3d_sjh_size", "https://www.8200.cn/kjh/3d/sjh.htm", {"size": 4000}),
    ("8200_pl3_sjh", "https://www.8200.cn/kjh/p3/sjh.htm", None),
    ("8200_pl3_sjh_size", "https://www.8200.cn/kjh/p3/sjh.htm", {"size": 4000}),
    ("3d178_year_2026", "https://www.3d178.cn/kaijiang/2026/", None),
    ("3d178_year_2025", "https://www.3d178.cn/kaijiang/2025/", None),
    ("3d178_sjh", "https://www.3d178.cn/shijihao/", None),
    ("3d178_sjh_page2", "https://www.3d178.cn/shijihao/index_2.shtml", None),
    ("ydniu_pl5_sjh", "https://m.ydniu.com/kaijiang/pl5/sjh.html", None),
    ("ydniu_pl5_sjh_page2", "https://m.ydniu.com/kaijiang/pl5/sjh_2.html", None),
    ("ydniu_pl5_kj", "https://m.ydniu.com/kaijiang/pl5/", None),
]

results = [probe(*case) for case in CASES]
OUT.joinpath("bulk_probe_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps([
    {k: x.get(k) for k in ["name", "status", "length", "title", "table_count", "row_count", "error"]}
    for x in results
], ensure_ascii=False, indent=2))
