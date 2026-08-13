from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import digits, fetch_text, iso_date


def _parse_boxes(text: str, list_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(text, "lxml")
    output: dict[str, dict[str, str]] = {}
    for box in soup.select(".sjhbox"):
        box_text = box.get_text(" ", strip=True)
        period_match = re.search(r"(20\d{5})期", box_text)
        if not period_match:
            continue
        period = period_match.group(1)
        draw_date = iso_date(box_text)
        draw_box = box.select_one(".balltopbox .ball_right")
        trial_box = box.select_one(".list_top")
        draw = digits(draw_box.get_text(" ", strip=True), 5) if draw_box else ""
        trial = digits(trial_box.get_text(" ", strip=True), 5) if trial_box else ""
        if not draw_date or not trial:
            continue
        item = {
            "period": period,
            "date_ydniu": draw_date.isoformat(),
            "draw_ydniu": draw,
            "trial5_ydniu": trial,
            "source_ydniu": f"https://m.ydniu.com/kaijiang/pl5/sjh/{period}.html",
            "source_ydniu_list": list_url,
        }
        previous = output.get(period)
        if previous is None or (not previous.get("draw_ydniu") and draw):
            output[period] = item
    return list(output.values())


def list_500() -> list[dict[str, str]]:
    url = "https://m.ydniu.com/kaijiang/pl5/sjh-500.html"
    text = fetch_text(url, "ydniu-list", "500", timeout=50)
    return _parse_boxes(text, url) if text else []


def period_detail(period: str) -> dict[str, str] | None:
    url = f"https://m.ydniu.com/kaijiang/pl5/sjh/{period}.html"
    text = fetch_text(url, "ydniu-period", period)
    if not text:
        return None
    for item in _parse_boxes(text, url):
        if item["period"] == period:
            return item
    return None
