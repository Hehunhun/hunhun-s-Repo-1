from __future__ import annotations

import csv
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

START_DATE = date(2023, 8, 13)
END_DATE = date(2026, 8, 13)
OUT = Path("lottery_output")
OUT.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)

_thread_local = threading.local()
_error_lock = threading.Lock()
ERRORS: list[dict[str, str]] = []


def add_error(stage: str, item: str, message: str, url: str = "") -> None:
    with _error_lock:
        ERRORS.append({
            "stage": stage,
            "item": item,
            "message": message[:1000],
            "url": url,
        })


def get_session() -> requests.Session:
    value = getattr(_thread_local, "session", None)
    if value is not None:
        return value
    value = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
    value.mount("https://", adapter)
    value.mount("http://", adapter)
    value.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        "Connection": "keep-alive",
    })
    _thread_local.session = value
    return value


def fetch_text(url: str, stage: str, item: str, timeout: int = 35) -> str | None:
    last: Exception | None = None
    for attempt in range(4):
        try:
            time.sleep(random.uniform(0.01, 0.06))
            response = get_session().get(url, timeout=(12, timeout), allow_redirects=True)
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]!r}")
            response.encoding = "utf-8"
            text = response.text
            if len(text) < 700:
                raise RuntimeError(f"response too short: {len(text)}")
            return text
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(0.4 * (2**attempt) + random.uniform(0.05, 0.35))
    add_error(stage, item, repr(last), url)
    return None


def digits(text: str, length: int) -> str:
    value = "".join(re.findall(r"\d", text))
    return value if len(value) == length else ""


def iso_date(text: str) -> date | None:
    patterns = (
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?",
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
    return None


def period7(text: str, href: str = "") -> str:
    match = re.search(r"(20\d{5})", href)
    if match:
        return match.group(1)
    value = "".join(re.findall(r"\d", text))
    if len(value) == 7 and value.startswith("20"):
        return value
    if len(value) == 5:
        return "20" + value
    return ""


def date_from_mmdd(period: str, text: str) -> date | None:
    match = re.search(r"(\d{1,2})-(\d{1,2})", text)
    if not match or len(period) != 7:
        return None
    try:
        return date(int(period[:4]), int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def run_parallel(
    name: str,
    items: Iterable[Any],
    fn: Callable[[Any], Any],
    workers: int = 14,
) -> list[Any]:
    sequence = list(items)
    output: list[Any] = []
    total = len(sequence)
    print(f"[{name}] start: {total} items; workers={workers}", flush=True)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name[:16]) as executor:
        futures = {executor.submit(fn, item): item for item in sequence}
        for index, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            try:
                result = future.result()
                if isinstance(result, list):
                    output.extend(result)
                elif result is not None:
                    output.append(result)
            except Exception as exc:
                add_error(name, str(item), repr(exc))
            if index % 50 == 0 or index == total:
                print(
                    f"[{name}] {index}/{total}; collected={len(output)}; errors={len(ERRORS)}",
                    flush=True,
                )
    return output


def best_by_period(
    records: Iterable[dict[str, str]],
    completeness: tuple[str, ...],
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for record in records:
        period = record.get("period", "")
        if not period:
            continue
        score = sum(bool(record.get(key)) for key in completeness)
        old = output.get(period)
        old_score = sum(bool(old.get(key)) for key in completeness) if old else -1
        if score > old_score:
            output[period] = record
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
