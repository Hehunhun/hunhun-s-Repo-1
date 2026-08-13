from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT = Path("probe_2026214_output")
OUT.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})

urls = {
    "8200_sjh": "https://www.8200.cn/kjh/3d/sjh.htm",
    "8200_sjh_30": "https://www.8200.cn/kjh/3d/sjh.htm?size=30",
    "8200_issue": "https://www.8200.cn/kjh/3d/2026214.htm",
    "3d178_sjh": "https://www.3d178.cn/shijihao/",
    "3d178_find": "https://www.3d178.cn/shijihao/find/",
    "3d178_issue": "https://www.3d178.cn/kaijiang/2026/2026214.shtml",
    "78500_sjh": "https://3d.78500.cn/shijihao.html",
    "78500_issue": "https://m.78500.cn/3d/view/2026214.html",
    "17500_data": "https://data.17500.cn/3d_desc.txt",
    "17500_chart": "https://www.17500.cn/chart/3d-qhgx.html",
}

results = {}
for name, url in urls.items():
    try:
        r = session.get(url, timeout=(15, 60), allow_redirects=True)
        raw = r.content
        # Try UTF-8 first, then apparent encoding.
        enc = r.encoding or r.apparent_encoding or "utf-8"
        try:
            text = raw.decode(enc, errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        OUT.joinpath(f"{name}.txt").write_text(text, encoding="utf-8", errors="replace")
        soup = BeautifulSoup(text, "lxml")
        plain = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        # Capture snippets around target issue and target numbers.
        snippets = {}
        for needle in ["2026214", "877", "758", "545", "试机号", "模拟试机号", "开机号"]:
            positions = [m.start() for m in re.finditer(re.escape(needle), plain)]
            snippets[needle] = [plain[max(0, p-260):p+520] for p in positions[:12]]
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(r.url, a["href"])
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if "2026214" in href or "2026214" in label or "试机" in label or "开奖" in label:
                links.append({"label": label[:120], "href": href})
        results[name] = {
            "url": url,
            "status": r.status_code,
            "final_url": r.url,
            "length": len(raw),
            "encoding": enc,
            "title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "snippets": snippets,
            "links": links[:100],
        }
    except Exception as exc:
        results[name] = {"url": url, "error": repr(exc)}

OUT.joinpath("results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2)[:120000])
