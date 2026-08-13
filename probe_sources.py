from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any

import requests

OUT = Path("probe_output")
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})


def compact(value: Any, max_chars: int = 12000) -> Any:
    if isinstance(value, dict):
        return {str(k): compact(v, max_chars=max_chars) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [compact(v, max_chars=max_chars) for v in value[:8]]
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "...<truncated>"
    return value


def fetch(name: str, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "url": url, "params": params}
    try:
        response = SESSION.get(url, params=params, timeout=(15, 45), allow_redirects=True)
        result.update({
            "status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("content-type", ""),
            "encoding": response.encoding,
            "apparent_encoding": response.apparent_encoding,
            "length": len(response.content),
            "headers": dict(response.headers),
        })
        raw_path = RAW / f"{name}.bin"
        raw_path.write_bytes(response.content)
        text = response.text
        (RAW / f"{name}.txt").write_text(text[:250_000], encoding="utf-8", errors="replace")
        result["text_head"] = re.sub(r"\s+", " ", text[:2500])
        try:
            payload = response.json()
            result["json"] = compact(payload)
            result["json_top_type"] = type(payload).__name__
            if isinstance(payload, dict):
                result["json_keys"] = list(payload.keys())
        except Exception as exc:
            result["json_error"] = repr(exc)
        return result
    except Exception as exc:
        result["error"] = repr(exc)
        result["traceback"] = traceback.format_exc()
        return result


probes: list[tuple[str, str, dict[str, Any] | None]] = [
    (
        "cwl_fc3d",
        "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
        {
            "name": "3d",
            "issueCount": "",
            "issueStart": "",
            "issueEnd": "",
            "dayStart": "2026-08-01",
            "dayEnd": "2026-08-13",
            "pageNo": 1,
            "pageSize": 50,
            "week": "",
            "systemType": "PC",
        },
    ),
    (
        "sporttery_pl3",
        "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry",
        {"gameNo": "350133", "provinceId": 0, "pageSize": 10, "pageNo": 1, "isVerify": 1, "termLimits": 0},
    ),
    (
        "sporttery_pl5",
        "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry",
        {"gameNo": "350135", "provinceId": 0, "pageSize": 10, "pageNo": 1, "isVerify": 1, "termLimits": 0},
    ),
    (
        "icaiwa_fc3d",
        "https://api.icaiwa.com/slotto/share/lotto/list",
        {"type": "fc3d", "page": 1, "limit": 10, "noneNull": 1},
    ),
    (
        "icaiwa_pl3",
        "https://api.icaiwa.com/slotto/share/lotto/list",
        {"type": "pl3", "page": 1, "limit": 10, "noneNull": 1},
    ),
    (
        "icaiwa_pl5",
        "https://api.icaiwa.com/slotto/share/lotto/list",
        {"type": "pl5", "page": 1, "limit": 10, "noneNull": 1},
    ),
    ("page_8200_fc3d_2025035", "https://www.8200.cn/kjh/3d/2025035.htm", None),
    ("page_00038_fc3d_2025035", "https://www.00038.cn/kjh/3d/2025035.htm", None),
    ("page_3d178_fc3d_2025035", "https://www.3d178.cn/kaijiang/2025/2025035.shtml", None),
    ("page_00038_pl3_2025035", "https://www.00038.cn/kjh/p3/2025035.htm", None),
    ("page_ydniu_pl5_2025146", "https://m.ydniu.com/kaijiang/pl5/sjh/2025146.html", None),
    ("page_78500_trial", "https://3d.78500.cn/shijihao.html", None),
]

results = [fetch(name, url, params) for name, url, params in probes]
OUT.joinpath("probe_results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(json.dumps([
    {
        "name": item["name"],
        "status": item.get("status"),
        "length": item.get("length"),
        "content_type": item.get("content_type"),
        "error": item.get("error"),
        "json_keys": item.get("json_keys"),
        "text_head": item.get("text_head", "")[:300],
    }
    for item in results
], ensure_ascii=False, indent=2))
