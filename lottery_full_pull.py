from __future__ import annotations

import csv
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

START_DATE = date(2023, 8, 13)
END_DATE = date(2026, 8, 13)
OUT = Path("lottery_output")
OUT.mkdir(parents=True, exist_ok=True)
ERROR_RAW = OUT / "error_raw"
ERROR_RAW.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)

THREAD_LOCAL = threading.local()
HOST_LIMITS = {
    "8200": threading.Semaphore(8),
    "3d178": threading.Semaphore(5),
    "ydniu": threading.Semaphore(6),
}
PRINT_LOCK = threading.Lock()


@dataclass
class SourceRecord:
    source: str
    game: str
    period: str
    draw_date: str = ""
    draw: str = ""
    trial: str = ""
    open_no: str = ""
    source_url: str = ""
    source_note: str = ""
    non_official: str = "否"
    status_code: int | None = None
    parse_ok: str = "否"
    error: str = ""


def get_session(host_key: str) -> requests.Session:
    sessions = getattr(THREAD_LOCAL, "sessions", None)
    if sessions is None:
        sessions = {}
        THREAD_LOCAL.sessions = sessions
    if host_key not in sessions:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Connection": "keep-alive",
        })
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=0)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        sessions[host_key] = session
    return sessions[host_key]


def fetch(url: str, host_key: str, referer: str, attempts: int = 3) -> tuple[int | None, bytes, str]:
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            time.sleep(random.uniform(0.015, 0.08))
            with HOST_LIMITS[host_key]:
                response = get_session(host_key).get(
                    url,
                    headers={"Referer": referer},
                    timeout=(12, 35),
                    allow_redirects=True,
                )
            if response.status_code == 200 and response.content:
                return response.status_code, response.content, ""
            last_error = f"HTTP {response.status_code}"
            if response.status_code in {404, 410}:
                return response.status_code, response.content, last_error
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        time.sleep(min(4.0, 0.6 * (2 ** (attempt - 1))) + random.uniform(0, 0.3))
    return None, b"", last_error


def only_digits(text: str) -> str:
    return "".join(re.findall(r"\d", text or ""))


def node_digits(nodes: Iterable) -> str:
    return only_digits("".join(node.get_text("", strip=True) for node in nodes))


def normalize_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def date_in_window(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        return START_DATE <= parsed <= END_DATE
    except ValueError:
        return False


def parse_8200(content: bytes, game: str, period: str, url: str, status: int | None) -> SourceRecord:
    record = SourceRecord(
        source="彩宝网/8200",
        game=game,
        period=period,
        source_url=url,
        status_code=status,
        source_note=(
            "福彩3D页面口径：同时列出开机号与试机号。"
            if game == "福彩3D"
            else "排列三页面所列三位试机号；排列三与排列五共用同一期体彩摇奖流程。"
        ),
    )
    try:
        html = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        page_text = soup.get_text(" ", strip=True)
        if period not in title and period not in page_text[:5000]:
            record.error = "页面未包含目标期号"
            return record

        main_box = soup.select_one(".ballBox.ball40")
        if main_box is None:
            record.error = "未找到主开奖号码容器"
            return record
        draw = node_digits(main_box.select("span.ball"))
        expected_len = 3
        if len(draw) < expected_len:
            record.error = f"开奖号码长度异常:{draw}"
            return record
        record.draw = draw[:expected_len]

        date_match = re.search(r"开奖时间[：:]\s*(\d{4}-\d{2}-\d{2})", page_text)
        if date_match:
            record.draw_date = normalize_date(date_match.group(1))

        if game == "福彩3D":
            open_match = re.search(r"\d{3}期开机号[：:]\s*([0-9\s]{3,12})", page_text)
            trial_match = re.search(r"\d{3}期试机号[：:]\s*([0-9\s]{3,12})", page_text)
            if open_match:
                record.open_no = only_digits(open_match.group(1))[:3]
            if trial_match:
                record.trial = only_digits(trial_match.group(1))[:3]
        else:
            trial_match = re.search(r"\d{3}期试机号[：:]\s*([0-9\s]{3,12})", page_text)
            if trial_match:
                record.trial = only_digits(trial_match.group(1))[:3]

        if not record.draw_date:
            record.error = "未解析到开奖日期"
            return record
        if not record.trial:
            record.error = "未解析到试机号"
            return record
        record.parse_ok = "是"
        return record
    except Exception as exc:  # noqa: BLE001
        record.error = f"解析异常:{exc!r}"
        return record


def parse_3d178(content: bytes, period: str, url: str, status: int | None) -> SourceRecord:
    record = SourceRecord(
        source="3D之家/3d178",
        game="福彩3D",
        period=period,
        source_url=url,
        status_code=status,
        source_note="3D之家页面所列试机号；与彩宝网口径可能不同，原样独立保留。",
    )
    try:
        html = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if period not in title and period not in soup.get_text(" ", strip=True)[:5000]:
            record.error = "页面未包含目标期号"
            return record
        table = soup.select_one("table.kjjg_table")
        if table is None:
            record.error = "未找到开奖信息表"
            return record
        record.draw = node_digits(table.select("li.ball_orange"))[:3]
        record.trial = node_digits(table.select("li.ball_red"))[:3]
        text = table.get_text(" ", strip=True)
        date_match = re.search(r"开奖日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if date_match:
            record.draw_date = date(
                int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
            ).isoformat()
        if len(record.draw) != 3 or len(record.trial) != 3 or not record.draw_date:
            record.error = f"字段不完整:date={record.draw_date},draw={record.draw},trial={record.trial}"
            return record
        record.parse_ok = "是"
        return record
    except Exception as exc:  # noqa: BLE001
        record.error = f"解析异常:{exc!r}"
        return record


def parse_ydniu(content: bytes, period: str, url: str, status: int | None) -> SourceRecord:
    record = SourceRecord(
        source="一定牛/ydniu",
        game="排列五",
        period=period,
        source_url=url,
        status_code=status,
        source_note="页面明确标注为排列五五位模拟试机号，属于互联网模拟数据，不是官方试机号。",
        non_official="是",
    )
    try:
        # 页面目前为 UTF-8；显式解码避免 requests 猜错编码。
        html = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        content_box = soup.select_one(".sjhcontent")
        if content_box is None or period not in title:
            record.error = "页面不是目标期号的排列五试机页"
            return record

        date_nodes = content_box.select(".sjhdate span")
        date_text = " ".join(node.get_text(" ", strip=True) for node in date_nodes)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        if date_match:
            record.draw_date = normalize_date(date_match.group(1))

        draw_nodes = content_box.select(".balltopbox .ball_right i.ball")
        record.draw = node_digits(draw_nodes)[:5]
        trial_nodes = content_box.select(".list_top > i")
        record.trial = node_digits(trial_nodes)[:5]

        if len(record.draw) != 5 or len(record.trial) != 5 or not record.draw_date:
            record.error = f"字段不完整:date={record.draw_date},draw={record.draw},trial={record.trial}"
            return record
        record.parse_ok = "是"
        return record
    except Exception as exc:  # noqa: BLE001
        record.error = f"解析异常:{exc!r}"
        return record


def make_periods() -> list[str]:
    periods: list[str] = []
    for year in range(2023, 2027):
        first = 215 if year == 2023 else 1
        last = 215 if year == 2026 else 366
        for seq in range(first, last + 1):
            periods.append(f"{year}{seq:03d}")
    return periods


def task_fc3d_8200(period: str) -> SourceRecord:
    url = f"https://www.8200.cn/kjh/3d/{period}.htm"
    status, content, error = fetch(url, "8200", "https://www.8200.cn/kjh/3d/history.htm")
    if not content:
        return SourceRecord(source="彩宝网/8200", game="福彩3D", period=period, source_url=url, status_code=status, error=error)
    record = parse_8200(content, "福彩3D", period, url, status)
    if record.parse_ok != "是" and status == 200 and len(content) < 20000:
        (ERROR_RAW / f"fc3d_8200_{period}.html").write_bytes(content)
    return record


def task_pl3_8200(period: str) -> SourceRecord:
    url = f"https://www.8200.cn/kjh/p3/{period}.htm"
    status, content, error = fetch(url, "8200", "https://www.8200.cn/kjh/p3/history.htm")
    if not content:
        return SourceRecord(source="彩宝网/8200", game="排列三", period=period, source_url=url, status_code=status, error=error)
    record = parse_8200(content, "排列三", period, url, status)
    if record.parse_ok != "是" and status == 200 and len(content) < 20000:
        (ERROR_RAW / f"pl3_8200_{period}.html").write_bytes(content)
    return record


def task_fc3d_3d178(period: str) -> SourceRecord:
    year = period[:4]
    url = f"https://www.3d178.cn/kaijiang/{year}/{period}.shtml"
    status, content, error = fetch(url, "3d178", f"https://www.3d178.cn/kaijiang/{year}/")
    if not content:
        return SourceRecord(source="3D之家/3d178", game="福彩3D", period=period, source_url=url, status_code=status, error=error)
    record = parse_3d178(content, period, url, status)
    if record.parse_ok != "是" and status == 200 and len(content) < 30000:
        (ERROR_RAW / f"fc3d_3d178_{period}.html").write_bytes(content)
    return record


def task_pl5_ydniu(period: str) -> SourceRecord:
    url = f"https://m.ydniu.com/kaijiang/pl5/sjh/{period}.html"
    status, content, error = fetch(url, "ydniu", "https://m.ydniu.com/kaijiang/pl5/sjh.html")
    if not content:
        return SourceRecord(
            source="一定牛/ydniu", game="排列五", period=period, source_url=url,
            status_code=status, error=error, non_official="是"
        )
    record = parse_ydniu(content, period, url, status)
    if record.parse_ok != "是" and status == 200 and len(content) < 30000:
        (ERROR_RAW / f"pl5_ydniu_{period}.html").write_bytes(content)
    return record


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first_nonempty(*values: str) -> str:
    return next((value for value in values if value), "")


def yes_no(condition: bool | None) -> str:
    if condition is None:
        return "无法校验"
    return "一致" if condition else "不一致"


def main() -> None:
    periods = make_periods()
    task_specs: list[tuple[Callable[[str], SourceRecord], str]] = []
    for period in periods:
        task_specs.extend([
            (task_fc3d_8200, period),
            (task_fc3d_3d178, period),
            (task_pl3_8200, period),
            (task_pl5_ydniu, period),
        ])

    records: list[SourceRecord] = []
    total = len(task_specs)
    started = time.time()
    with ThreadPoolExecutor(max_workers=24) as executor:
        futures = [executor.submit(func, period) for func, period in task_specs]
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                records.append(future.result())
            except Exception as exc:  # noqa: BLE001
                records.append(SourceRecord(source="worker", game="未知", period="", error=repr(exc)))
            if index % 100 == 0 or index == total:
                with PRINT_LOCK:
                    ok_count = sum(1 for row in records if row.parse_ok == "是")
                    print(f"progress {index}/{total}; parsed={ok_count}; elapsed={time.time()-started:.1f}s", flush=True)

    raw_rows = [asdict(record) for record in sorted(records, key=lambda row: (row.period, row.game, row.source))]
    write_csv(OUT / "00_source_records.csv", raw_rows)

    valid = [row for row in records if row.parse_ok == "是" and date_in_window(row.draw_date)]
    fc8200 = {row.period: row for row in valid if row.game == "福彩3D" and row.source == "彩宝网/8200"}
    fc178 = {row.period: row for row in valid if row.game == "福彩3D" and row.source == "3D之家/3d178"}
    pl3map = {row.period: row for row in valid if row.game == "排列三" and row.source == "彩宝网/8200"}
    pl5map = {row.period: row for row in valid if row.game == "排列五" and row.source == "一定牛/ydniu"}

    fc3d_rows: list[dict] = []
    for period in sorted(set(fc8200) | set(fc178)):
        a = fc8200.get(period)
        b = fc178.get(period)
        draw_a = a.draw if a else ""
        draw_b = b.draw if b else ""
        date_a = a.draw_date if a else ""
        date_b = b.draw_date if b else ""
        fc3d_rows.append({
            "开奖日期": first_nonempty(date_a, date_b),
            "期号": period,
            "开奖号": first_nonempty(draw_a, draw_b),
            "开奖号_彩宝网": draw_a,
            "开奖号_3D之家": draw_b,
            "开机号_彩宝网": a.open_no if a else "",
            "试机号_彩宝网": a.trial if a else "",
            "试机号_3D之家": b.trial if b else "",
            "两来源开奖号校验": yes_no(None if not draw_a or not draw_b else draw_a == draw_b),
            "两来源日期校验": yes_no(None if not date_a or not date_b else date_a == date_b),
            "彩宝网来源": a.source_url if a else f"https://www.8200.cn/kjh/3d/{period}.htm",
            "3D之家来源": b.source_url if b else f"https://www.3d178.cn/kaijiang/{period[:4]}/{period}.shtml",
        })

    pl3_rows: list[dict] = []
    for period, row in sorted(pl3map.items()):
        pl3_rows.append({
            "开奖日期": row.draw_date,
            "期号": period,
            "开奖号": row.draw,
            "试机号_彩宝网": row.trial,
            "来源": row.source_url,
        })

    pl5_rows: list[dict] = []
    for period, row in sorted(pl5map.items()):
        shared = pl3map.get(period)
        pl5_rows.append({
            "开奖日期": row.draw_date,
            "期号": period,
            "开奖号": row.draw,
            "前三位开奖号": row.draw[:3],
            "共享三位试机号_取自排列三彩宝网": shared.trial if shared else "",
            "五位模拟试机号_一定牛": row.trial,
            "模拟号是否非官方": "是",
            "一定牛来源": row.source_url,
            "排列三来源": shared.source_url if shared else f"https://www.8200.cn/kjh/p3/{period}.htm",
        })

    by_date_fc = {row["开奖日期"]: row for row in fc3d_rows if row["开奖日期"]}
    by_date_p3 = {row["开奖日期"]: row for row in pl3_rows if row["开奖日期"]}
    by_date_p5 = {row["开奖日期"]: row for row in pl5_rows if row["开奖日期"]}
    dates = sorted(set(by_date_fc) | set(by_date_p3) | set(by_date_p5))
    aligned_rows: list[dict] = []
    quality_rows: list[dict] = []

    for draw_date in dates:
        fc = by_date_fc.get(draw_date, {})
        p3 = by_date_p3.get(draw_date, {})
        p5 = by_date_p5.get(draw_date, {})
        p3_draw = p3.get("开奖号", "")
        p5_draw = p5.get("开奖号", "")
        prefix_check = None if not p3_draw or not p5_draw else p3_draw == p5_draw[:3]
        complete = all([
            fc.get("开奖号"), fc.get("试机号_彩宝网"), fc.get("试机号_3D之家"),
            p3_draw, p3.get("试机号_彩宝网"), p5_draw, p5.get("五位模拟试机号_一定牛")
        ])
        aligned_rows.append({
            "开奖日期": draw_date,
            "福彩3D期号": fc.get("期号", ""),
            "福彩3D开奖号": fc.get("开奖号", ""),
            "福彩3D开机号_彩宝网": fc.get("开机号_彩宝网", ""),
            "福彩3D试机号_彩宝网": fc.get("试机号_彩宝网", ""),
            "福彩3D试机号_3D之家": fc.get("试机号_3D之家", ""),
            "体彩期号": first_nonempty(p3.get("期号", ""), p5.get("期号", "")),
            "排列三开奖号": p3_draw,
            "排列三试机号_彩宝网": p3.get("试机号_彩宝网", ""),
            "排列五开奖号": p5_draw,
            "排列五共享三位试机号": p5.get("共享三位试机号_取自排列三彩宝网", ""),
            "排列五五位模拟试机号_一定牛": p5.get("五位模拟试机号_一定牛", ""),
            "排列三等于排列五前三位": yes_no(prefix_check),
            "福彩3D两来源开奖号一致": fc.get("两来源开奖号校验", "无法校验"),
            "完整记录": "是" if complete else "否",
            "福彩3D彩宝网来源": fc.get("彩宝网来源", ""),
            "福彩3D之家来源": fc.get("3D之家来源", ""),
            "排列三来源": p3.get("来源", ""),
            "排列五来源": p5.get("一定牛来源", ""),
        })
        if not complete or prefix_check is False or fc.get("两来源开奖号校验") == "不一致":
            quality_rows.append({
                "开奖日期": draw_date,
                "问题类型": ";".join(filter(None, [
                    "字段缺失" if not complete else "",
                    "排列三与排列五前三位不一致" if prefix_check is False else "",
                    "福彩3D两来源开奖号不一致" if fc.get("两来源开奖号校验") == "不一致" else "",
                ])),
                "福彩3D期号": fc.get("期号", ""),
                "体彩期号": first_nonempty(p3.get("期号", ""), p5.get("期号", "")),
                "说明": "需结合来源页面人工复核。",
            })

    write_csv(OUT / "01_fc3d.csv", fc3d_rows)
    write_csv(OUT / "02_pl3.csv", pl3_rows)
    write_csv(OUT / "03_pl5.csv", pl5_rows)
    write_csv(OUT / "04_aligned_by_date.csv", aligned_rows)
    write_csv(OUT / "05_quality_issues.csv", quality_rows, ["开奖日期", "问题类型", "福彩3D期号", "体彩期号", "说明"])

    failed = [row for row in raw_rows if row["parse_ok"] != "是"]
    failed_relevant = [
        row for row in failed
        if row["status_code"] not in {404, 410} and not (row["error"] or "").startswith("页面未包含目标期号")
    ]
    summary = {
        "date_window": {"start": START_DATE.isoformat(), "end": END_DATE.isoformat()},
        "candidate_periods": len(periods),
        "source_requests": len(records),
        "valid_source_records_in_window": len(valid),
        "fc3d_periods": len(fc3d_rows),
        "pl3_periods": len(pl3_rows),
        "pl5_periods": len(pl5_rows),
        "aligned_dates": len(aligned_rows),
        "complete_aligned_dates": sum(1 for row in aligned_rows if row["完整记录"] == "是"),
        "quality_issue_dates": len(quality_rows),
        "non_404_parse_or_request_failures": len(failed_relevant),
        "elapsed_seconds": round(time.time() - started, 2),
        "notes": [
            "福彩3D保留彩宝网和3D之家两套试机号口径，不做强行合并。",
            "排列五五位试机号来自一定牛模拟页面，明确标记为非官方模拟数据。",
            "排列五共享三位试机号直接引用同期开奖日期/期号的排列三试机号。",
            "所有号码按文本保存，以保留前导0。",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "failures.json").write_text(json.dumps(failed_relevant, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
