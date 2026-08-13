from __future__ import annotations

import json
import re
from pathlib import Path

import requests

OUT = Path("year_route_probe_output")
OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})

results = []
js_url = "https://static.8200.cn/www8200/static/js/common.js?v=2021082007"
r = s.get(js_url, timeout=(12, 40))
r.encoding = r.apparent_encoding or "utf-8"
js = r.text
(OUT / "8200_common.js").write_text(js, encoding="utf-8", errors="replace")
contexts = []
for match in re.finditer(r"getqilist|s_year|history\.htm|/ajax/", js, re.I):
    contexts.append(js[max(0, match.start()-700):min(len(js), match.end()+1600)])
results.append({"name": "common_js", "status": r.status_code, "length": len(r.content), "contexts": contexts[:50]})

candidates = []
for game in ["3d", "p3", "p5"]:
    for url in [
        f"https://www.8200.cn/kjh/{game}/history.htm?size=300",
        f"https://www.8200.cn/kjh/{game}/history.htm?year=2025",
        f"https://www.8200.cn/kjh/{game}/history.htm?year=2025&size=300",
        f"https://www.8200.cn/kjh/{game}/2025/history.htm",
        f"https://www.8200.cn/kjh/{game}/history_2025.htm",
        f"https://www.8200.cn/kjh/{game}/history2025.htm",
    ]:
        try:
            q = s.get(url, timeout=(12, 40), allow_redirects=True)
            text = q.text
            candidates.append({
                "url": url,
                "status": q.status_code,
                "final_url": q.url,
                "length": len(q.content),
                "has_2025": "2025年" in text,
                "has_2026": "2026年" in text,
                "periods_2025": len(set(re.findall(r"2025\d{3}", text))),
                "periods_2026": len(set(re.findall(r"2026\d{3}", text))),
                "rows": text.count("<tr"),
                "title": re.search(r"<title>(.*?)</title>", text, re.I|re.S).group(1).strip() if re.search(r"<title>(.*?)</title>", text, re.I|re.S) else "",
            })
        except Exception as exc:
            candidates.append({"url": url, "error": repr(exc)})
results.append({"name": "candidate_routes", "items": candidates})

(OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
