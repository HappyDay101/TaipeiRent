import json
import os
import random
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
DEFAULT_KEYWORDS = ["大安", "東門", "大安森林公園", "中山", "中正", "大同"]
SEEN_IDS_FILE = Path("seen_ids.json")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Rent591Watcher:
    def __init__(
        self,
        url: str,
        wanted_pages: int = 2,
        max_price: int = 35000,
        keywords: list[str] | None = None,
        seen_ids_file: Path = SEEN_IDS_FILE,
        discord_webhook_url: str | None = None,
        dry_run: bool = False,
        mark_seen_only: bool = False,
        send_empty_status: bool = False,
    ) -> None:
        self.search_url = self._normalize_search_url(url)
        self.wanted_pages = wanted_pages
        self.max_price = max_price
        self.keywords = keywords or DEFAULT_KEYWORDS
        self.seen_ids_file = seen_ids_file
        self.discord_webhook_url = discord_webhook_url
        self.dry_run = dry_run
        self.mark_seen_only = mark_seen_only
        self.send_empty_status = send_empty_status
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _normalize_search_url(self, url: str) -> str:
        cleaned = url.replace("&sort=posttime_desc", "").replace("sort=posttime_desc", "")
        separator = "&" if "?" in cleaned else "?"
        return f"{cleaned}{separator}sort=posttime_desc"

    def _sleep(self, minimum: float = 1.0, maximum: float = 2.0) -> None:
        time.sleep(random.uniform(minimum, maximum))

    def get_house_ids(self) -> list[str]:
        house_ids: list[str] = []

        for page in range(1, self.wanted_pages + 1):
            page_url = self.search_url if page == 1 else f"{self.search_url}&page={page}"
            response = self.session.get(page_url, headers=DEFAULT_HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_ids: list[str] = []
            for link in soup.find_all("a", href=True):
                house_id = self._extract_house_id_from_href(link["href"])
                if house_id:
                    page_ids.append(house_id)
            house_ids.extend(page_ids)
            self._sleep()

        unique_ids = list(dict.fromkeys(house_ids))
        print(f"Fetched {len(unique_ids)} listing ids")
        return unique_ids

    def _extract_house_id_from_href(self, href: str) -> str | None:
        match = re.search(r"rent\.591\.com\.tw/(\d+)(?:[/?#]|$)", href)
        if match:
            return match.group(1)
        match = re.fullmatch(r"/?(\d+)", href)
        if match:
            return match.group(1)
        return None

    def get_house_detail(self, house_id: str) -> str | None:
        detail_page_url = f"https://rent.591.com.tw/{house_id}"
        detail_page_response = self.session.get(detail_page_url, headers=DEFAULT_HEADERS)
        detail_page_response.raise_for_status()
        self._sleep()
        html = detail_page_response.text
        if "591租屋網" not in html:
            print(f"Skipping {house_id}: unexpected detail page.")
            return None
        return html

    def normalize_listing(self, house_id: str, house_html: str) -> dict:
        soup = BeautifulSoup(house_html, "html.parser")
        page_text = soup.get_text("\n", strip=True)
        summary_text = self._extract_summary_text(page_text)

        title = (
            self._extract_meta_content(soup, "property", "og:title")
            or self._extract_first_heading(soup)
            or f"591 租屋 {house_id}"
        )
        title = title.replace(" - 591租屋網", "").strip()
        price = self._extract_price(page_text)
        address = self._extract_address(page_text)
        location = address.replace("台北市", "", 1) if address else ""
        description = self._extract_description(page_text)
        kind = self._extract_kind(summary_text)
        shape = self._extract_shape(summary_text)
        floor = self._extract_floor(summary_text)
        room = self._extract_room_text(summary_text)
        tags = [value for value in [kind, shape, floor, room] if value]
        combined_text = " ".join([title, location, description, summary_text, " ".join(tags)])

        return {
            "id": house_id,
            "title": title,
            "price": price,
            "location": location,
            "description": description,
            "kind": kind,
            "shape": shape,
            "floor": floor,
            "room": room,
            "post_time": self._extract_post_time(page_text),
            "update_time": "",
            "link": f"https://rent.591.com.tw/{house_id}",
            "combined_text": combined_text,
        }

    def _extract_meta_content(self, soup: BeautifulSoup, attr_name: str, attr_value: str) -> str:
        tag = soup.find("meta", attrs={attr_name: attr_value})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return ""

    def _extract_first_heading(self, soup: BeautifulSoup) -> str:
        heading = soup.find(["h1", "h2"])
        return heading.get_text(" ", strip=True) if heading else ""

    def _extract_summary_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line in {"整層住家", "獨立套房", "分租套房", "雅房"}:
                return " ".join(lines[index:index + 6])
            if any(kind in line for kind in ["整層住家", "獨立套房", "分租套房", "雅房"]):
                return " ".join(lines[index:index + 4])
        return text

    def _extract_price(self, text: str) -> int:
        match = re.search(r"([\d,]+)\s*元/月", text)
        if not match:
            return 0
        return self._parse_price(match.group(1))

    def _extract_address(self, text: str) -> str:
        patterns = [
            r"地\s*址[:：]?\s*\n\s*([^\n]+)",
            r"(台北市[^\n]+區[^\n]+)",
            r"([^\n]+區-[^\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_description(self, text: str) -> str:
        match = re.search(r"##\s*屋況介紹\s*(.*?)\s*##\s*房屋詳情", text, re.DOTALL)
        if match:
            return " ".join(line.strip() for line in match.group(1).splitlines() if line.strip())
        return ""

    def _extract_kind(self, text: str) -> str:
        for candidate in ["整層住家", "獨立套房", "分租套房", "雅房"]:
            if candidate in text:
                return candidate
        return ""

    def _extract_shape(self, text: str) -> str:
        for candidate in ["電梯大樓", "公寓", "透天厝", "別墅", "華廈"]:
            if candidate in text:
                return candidate
        return ""

    def _extract_floor(self, text: str) -> str:
        match = re.search(r"(\d+F/\d+F)", text)
        return match.group(1) if match else ""

    def _extract_room_text(self, text: str) -> str:
        match = re.search(r"(\d+房(?:\d+廳)?(?:\d+衛)?)", text)
        return match.group(1) if match else ""

    def _extract_post_time(self, text: str) -> str:
        match = re.search(r"此房屋在([^\n]+)發佈", text)
        return match.group(1).strip() if match else ""

    def _parse_price(self, raw_price) -> int:
        if isinstance(raw_price, (int, float)):
            return int(raw_price)
        if raw_price is None:
            return 0
        digits = "".join(ch for ch in str(raw_price) if ch.isdigit())
        return int(digits) if digits else 0

    def matches_filters(self, listing: dict) -> bool:
        if listing["price"] <= 0 or listing["price"] > self.max_price:
            return False

        text = listing["combined_text"]

        if self.keywords and not any(keyword in text for keyword in self.keywords):
            return False

        if "電梯" not in text:
            return False

        if listing.get("kind") != "整層住家":
            return False

        return True

    def format_message(self, listing: dict) -> str:
        bedroom_note = f" | {listing['room']}" if listing.get("room") else ""
        return (
            f"{listing['title']}\n"
            f"租金: {listing['price']:,} TWD{bedroom_note}\n"
            f"地點: {listing['location']}\n"
            f"{listing['link']}"
        )

    def load_seen_ids(self) -> set[str]:
        if not self.seen_ids_file.exists():
            return set()
        try:
            data = json.loads(self.seen_ids_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("seen_ids.json is invalid, starting fresh.")
            return set()
        if not isinstance(data, list):
            return set()
        return {str(item) for item in data}

    def save_seen_ids(self, seen_ids: set[str]) -> None:
        sorted_ids = sorted(seen_ids)
        self.seen_ids_file.write_text(
            json.dumps(sorted_ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def send_discord_message(self, text: str) -> None:
        if not self.discord_webhook_url:
            raise RuntimeError("DISCORD_WEBHOOK_URL is required when DRY_RUN is false.")
        response = requests.post(
            self.discord_webhook_url,
            json={"content": text},
            timeout=30,
        )
        response.raise_for_status()

    def notify(self, listing: dict) -> None:
        message = self.format_message(listing)
        if self.dry_run:
            print("\n--- MATCH ---")
            print(message)
            return
        self.send_discord_message(message)

    def notify_no_new_listing(self) -> None:
        message = "No new listing found / 未找到新房源"
        if self.dry_run:
            print(f"\n--- STATUS ---\n{message}")
            return
        self.send_discord_message(message)

    def run(self) -> None:
        seen_ids = self.load_seen_ids()
        house_ids = self.get_house_ids()

        matched_count = 0
        new_count = 0
        marked_count = 0

        for house_id in house_ids:
            if house_id in seen_ids:
                continue

            house_detail = self.get_house_detail(house_id)
            if not house_detail:
                continue

            listing = self.normalize_listing(house_id, house_detail)
            if not self.matches_filters(listing):
                continue

            matched_count += 1
            if self.mark_seen_only:
                seen_ids.add(house_id)
                marked_count += 1
                continue

            self.notify(listing)
            new_count += 1
            if not self.dry_run:
                seen_ids.add(house_id)
            time.sleep(0.2)

        if not self.dry_run or self.mark_seen_only:
            self.save_seen_ids(seen_ids)
        if self.mark_seen_only:
            print(f"Matched {matched_count} listings, marked {marked_count} as seen, sent 0 notifications.")
            return
        if new_count == 0 and self.send_empty_status:
            self.notify_no_new_listing()
        print(f"Matched {matched_count} listings, sent {new_count} new notifications.")


def main() -> None:
    url = require_env("URL")
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("URL must start with http:// or https://")
    wanted_pages = int(os.getenv("WANTED_PAGES", "2"))
    max_price = int(os.getenv("MAX_PRICE", "35000"))
    keywords_raw = os.getenv("KEYWORDS", ",".join(DEFAULT_KEYWORDS))
    keywords = [item.strip() for item in keywords_raw.split(",") if item.strip()]
    dry_run = env_flag("DRY_RUN", default=False)
    mark_seen_only = env_flag("MARK_SEEN_ONLY", default=False)
    send_empty_status = env_flag("SEND_EMPTY_STATUS", default=False)

    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    watcher = Rent591Watcher(
        url=url,
        wanted_pages=wanted_pages,
        max_price=max_price,
        keywords=keywords,
        discord_webhook_url=discord_webhook_url,
        dry_run=dry_run,
        mark_seen_only=mark_seen_only,
        send_empty_status=send_empty_status,
    )
    watcher.run()


if __name__ == "__main__":
    main()
