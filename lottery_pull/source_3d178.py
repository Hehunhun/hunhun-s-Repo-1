from __future__ import annotations

from bs4 import BeautifulSoup

from .common import digits, fetch_text, period7


def find_trial(trial: str, target_periods: set[str]) -> list[dict[str, str]]:
    url = f"https://www.3d178.cn/shijihao/find/{trial}.shtml"
    text = fetch_text(url, "3d178-find", trial)
    if not text:
        return []
    soup = BeautifulSoup(text, "lxml")
    table = None
    for candidate in soup.find_all("table"):
        content = candidate.get_text(" ", strip=True)
        if "开奖期号" in content and "试机号" in content:
            table = candidate
            break
    if table is None:
        return []
    output: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        period = period7(cells[0].get_text(" ", strip=True))
        draw = digits(cells[1].get_text(" ", strip=True), 3)
        trial_value = digits(cells[2].get_text(" ", strip=True), 3)
        if period in target_periods and draw and trial_value:
            output.append({
                "period": period,
                "draw_3d178_trial": draw,
                "trial_3d178": trial_value,
                "source_3d178": url,
            })
    return output


def period_fallback(period: str) -> dict[str, str] | None:
    year = period[:4]
    url = f"https://www.3d178.cn/kaijiang/{year}/{period}.shtml"
    text = fetch_text(url, "3d178-period-fallback", period, timeout=50)
    if not text:
        return None
    soup = BeautifulSoup(text, "lxml")
    draw_box = soup.select_one(".ball_box01")
    trial_box = soup.select_one(".ball_box02")
    draw = digits(draw_box.get_text(" ", strip=True), 3) if draw_box else ""
    trial = digits(trial_box.get_text(" ", strip=True), 3) if trial_box else ""
    if not draw or not trial:
        return None
    return {
        "period": period,
        "draw_3d178_trial": draw,
        "trial_3d178": trial,
        "source_3d178": url,
    }
