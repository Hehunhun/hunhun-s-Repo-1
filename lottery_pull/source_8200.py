from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import END_DATE, START_DATE, date_from_mmdd, digits, fetch_text, iso_date, period7


def history(game: str) -> list[dict[str, str]]:
    url = f"https://www.8200.cn/kjh/{game}/history.htm?size=300"
    text = fetch_text(url, f"8200-{game}-history", "size-300")
    if not text:
        return []
    soup = BeautifulSoup(text, "lxml")
    table = soup.find("table", class_="kjhTable")
    if table is None:
        return []
    output: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        link = row.find("a", href=True)
        href = link.get("href", "") if link else ""
        period = period7(cells[0].get_text(" ", strip=True), href)
        draw_date = date_from_mmdd(period, cells[1].get_text(" ", strip=True)) if len(cells) > 1 else None
        if not period or not draw_date:
            continue
        if game == "3d" and len(cells) >= 5:
            draw = digits(cells[2].get_text(" ", strip=True), 3)
            open_no = digits(cells[3].get_text(" ", strip=True), 3)
            trial = digits(cells[4].get_text(" ", strip=True), 3)
            if draw:
                output.append({
                    "period": period,
                    "date_8200": draw_date.isoformat(),
                    "draw_8200": draw,
                    "open_8200": open_no,
                    "trial_8200": trial,
                    "source_8200": url,
                })
        elif game == "p3" and len(cells) >= 4:
            draw = digits(cells[2].get_text(" ", strip=True), 3)
            trial = digits(cells[3].get_text(" ", strip=True), 3)
            if draw:
                output.append({
                    "period": period,
                    "date_8200": draw_date.isoformat(),
                    "draw_8200": draw,
                    "trial_8200": trial,
                    "source_8200": url,
                })
        elif game == "p5" and len(cells) >= 4:
            draw = digits(cells[2].get_text(" ", strip=True), 5)
            trial3 = digits(cells[3].get_text(" ", strip=True), 3)
            if draw:
                output.append({
                    "period": period,
                    "date_8200": draw_date.isoformat(),
                    "draw_8200": draw,
                    "trial3_8200": trial3,
                    "source_8200": url,
                })
    return output


def period_detail(game: str, period: str) -> dict[str, str] | None:
    url = f"https://www.8200.cn/kjh/{game}/{period}.htm"
    text = fetch_text(url, f"8200-{game}-period", period)
    if not text:
        return None
    soup = BeautifulSoup(text, "lxml")
    box = soup.select_one("div.ballBox.ball40")
    if box is None:
        return None
    expected = 3 if game in {"3d", "p3"} else 5
    draw = digits(box.get_text(" ", strip=True), expected)
    page_text = soup.get_text(" ", strip=True)
    draw_date = iso_date(page_text)
    if not draw or not draw_date or not (START_DATE <= draw_date <= END_DATE):
        return None
    if game == "3d":
        open_match = re.search(r"\d{3}期开机号\s*[:：]\s*(\d{3})", page_text)
        trial_match = re.search(r"\d{3}期试机号\s*[:：]\s*(\d{3})", page_text)
        return {
            "period": period,
            "date_8200": draw_date.isoformat(),
            "draw_8200": draw,
            "open_8200": open_match.group(1) if open_match else "",
            "trial_8200": trial_match.group(1) if trial_match else "",
            "source_8200": url,
        }
    if game == "p3":
        trial_match = re.search(r"\d{3}期试机号\s*[:：]\s*(\d{3})", page_text)
        return {
            "period": period,
            "date_8200": draw_date.isoformat(),
            "draw_8200": draw,
            "trial_8200": trial_match.group(1) if trial_match else "",
            "source_8200": url,
        }
    return None
