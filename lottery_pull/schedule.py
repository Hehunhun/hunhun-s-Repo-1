from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup

from .common import END_DATE, START_DATE, digits, fetch_text, iso_date, period7


def _year_page(year: int, page: int) -> list[dict[str, str]]:
    suffix = "" if page == 1 else f"index{page}.shtml"
    url = f"https://www.3d178.cn/kaijiang/{year}/{suffix}"
    text = fetch_text(url, "schedule", f"{year}-page-{page}")
    if not text:
        return []
    soup = BeautifulSoup(text, "lxml")
    table = soup.find("table", class_="tabkj")
    if table is None:
        return []
    output: list[dict[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        link = cells[0].find("a", href=True)
        href = link.get("href", "") if link else ""
        period = period7(cells[0].get_text(" ", strip=True), href)
        draw = digits(cells[1].get_text(" ", strip=True), 3)
        draw_date = iso_date(cells[2].get_text(" ", strip=True))
        if period and draw and draw_date:
            output.append({
                "period": period,
                "date": draw_date.isoformat(),
                "draw_3d178_year": draw,
                "source_schedule": url,
            })
    return output


def load_schedule() -> list[dict[str, str]]:
    collected: dict[str, dict[str, str]] = {}
    for year in range(START_DATE.year, END_DATE.year + 1):
        seen: set[str] = set()
        for page in range(1, 10):
            records = _year_page(year, page)
            fresh = [item for item in records if item["period"] not in seen]
            if not fresh:
                break
            for item in fresh:
                seen.add(item["period"])
                collected[item["period"]] = item
        print(f"[schedule] {year}: {len(seen)} periods", flush=True)
    selected = [
        item
        for item in collected.values()
        if START_DATE <= date.fromisoformat(item["date"]) <= END_DATE
    ]
    selected.sort(key=lambda item: (item["date"], item["period"]))
    if len(selected) < 900:
        raise RuntimeError(f"schedule unexpectedly short: {len(selected)}")
    return selected
