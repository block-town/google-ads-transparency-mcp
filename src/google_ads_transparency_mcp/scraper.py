"""Google Ads Transparency Center scraper.

Reverse-engineers Google's internal RPC endpoints to fetch advertiser info,
ad creatives, and ad details without an official API.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

import requests

from .parser import decode_text_ad
from .regions import REGIONS

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

BASE_URL = "https://adstransparency.google.com"


class GoogleAdsTransparency:
    """Client for the Google Ads Transparency Center."""

    def __init__(self, region: str = "anywhere", proxy: dict[str, str] | None = None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if proxy:
            self.session.proxies.update(proxy)

        self._region = region
        self._region_num = 0
        self._use_region = region != "anywhere"
        if self._use_region:
            if region not in REGIONS:
                raise ValueError(
                    f"Region '{region}' is not supported. "
                    f"Use one of: {', '.join(sorted(REGIONS.keys()))}"
                )
            self._region_num = REGIONS[region]["1"]

        self._get_cookies()

    def _get_cookies(self) -> None:
        self.session.get(BASE_URL, params={"region": self._region})

    def refresh_session(self, proxy: dict[str, str] | None = None) -> None:
        """Refresh session cookies, optionally updating the proxy."""
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        if proxy:
            self.session.proxies.update(proxy)
        self._get_cookies()

    # --- Search endpoints ---

    def search_suggestions(self, keyword: str) -> list[dict[str, Any]]:
        """Search for advertisers/domains matching a keyword."""
        data = {"f.req": json.dumps({"1": keyword, "2": 10, "3": 10})}
        resp = self.session.post(
            f"{BASE_URL}/anji/_/rpc/SearchService/SearchSuggestions",
            params={"authuser": "0"},
            data=data,
        )
        try:
            return resp.json().get("1", []) or []
        except (requests.exceptions.JSONDecodeError, ValueError):
            return []

    def search_advertiser_by_domain(self, domain: str) -> dict[str, Any] | None:
        """Find an advertiser by domain name.

        Returns {advertiser_id, name, ad_count} or None.
        """
        # Domain search requires domain in both field "1" and "3.12.1"
        req_body = {
            "1": domain,
            "2": 1,
            "3": {"12": {"1": domain}},
            "7": {"1": 1},
        }
        resp = self.session.post(
            f"{BASE_URL}/anji/_/rpc/SearchService/SearchCreatives",
            params={"authuser": ""},
            data={"f.req": json.dumps(req_body)},
        )
        try:
            results = resp.json().get("1")
        except (requests.exceptions.JSONDecodeError, ValueError):
            return None

        if not results:
            return None

        ad = results[0]
        advertiser_id = ad.get("1", "")
        name = ad.get("12", "")

        # Try to get ad count via suggestion search
        ad_count = self._get_ad_count(name, advertiser_id)

        return {
            "advertiser_id": advertiser_id,
            "name": name,
            "ad_count": ad_count,
        }

    def search_advertisers(self, query: str) -> list[dict[str, Any]]:
        """Search for advertisers by keyword.

        Returns a list of {advertiser_id, name, region, ad_count} dicts.
        """
        suggestions = self.search_suggestions(query)
        results = []
        for suggestion in suggestions:
            if "1" in suggestion:
                info = suggestion["1"]
                ad_count = 0
                if info.get("4", {}).get("2", {}).get("2"):
                    ad_count = int(info["4"]["2"]["2"])
                results.append({
                    "advertiser_id": info.get("2", ""),
                    "name": info.get("1", ""),
                    "region": info.get("3", ""),
                    "ad_count": ad_count,
                })
            elif "2" in suggestion:
                # Domain result — resolve to advertiser
                domain = suggestion["2"].get("1", "")
                if domain:
                    adv = self.search_advertiser_by_domain(domain)
                    if adv:
                        results.append({**adv, "domain": domain})
        return results

    # --- Creative endpoints ---

    def get_creative_ids(
        self, advertiser_id: str, count: int = 40, next_page_id: str = ""
    ) -> list[str]:
        """Get creative IDs for an advertiser."""
        req_body: dict[str, Any] = {
            "2": min(count, 100),
            "3": {"12": {"1": "", "2": True}, "13": {"1": [advertiser_id]}},
            "7": {"1": 1},
        }
        if next_page_id:
            req_body["4"] = next_page_id
        if self._use_region:
            req_body["3"]["8"] = [self._region_num]

        resp = self.session.post(
            f"{BASE_URL}/anji/_/rpc/SearchService/SearchCreatives",
            params={"authuser": ""},
            data={"f.req": json.dumps(req_body)},
        )
        try:
            res = resp.json()
        except (requests.exceptions.JSONDecodeError, ValueError):
            return []

        ads = res.get("1", [])
        ids = [ad["2"] for ad in ads if "2" in ad]
        next_token = res.get("2")

        if count <= 100 or not ids or next_token is None:
            return ids[:count]

        remaining = count - len(ids)
        ids.extend(self.get_creative_ids(advertiser_id, remaining, next_token))
        return ids

    def get_ad_detail(self, advertiser_id: str, creative_id: str) -> dict[str, Any]:
        """Get full details for a single ad creative."""
        data = {
            "f.req": json.dumps(
                {"1": advertiser_id, "2": creative_id, "5": {"1": 1}}
            ),
        }
        resp = self.session.post(
            f"{BASE_URL}/anji/_/rpc/LookupService/GetCreativeById",
            params={"authuser": "0"},
            data=data,
        )
        try:
            ad = resp.json()["1"]
        except (KeyError, TypeError, requests.exceptions.JSONDecodeError, ValueError):
            return {
                "advertiser_id": advertiser_id,
                "creative_id": creative_id,
                "format": "unknown",
                "last_shown": "",
                "content": {},
            }

        format_int = ad.get("8", 0)
        format_name = {1: "text", 2: "image", 3: "video"}.get(
            format_int, f"unknown ({format_int})"
        )

        # Extract date
        last_shown = ""
        try:
            last_shown = datetime.datetime.fromtimestamp(
                int(ad["4"]["1"])
            ).strftime("%Y-%m-%d")
        except (KeyError, TypeError, ValueError):
            pass

        # Extract ad link
        link = self._extract_ad_link(ad)

        # Build content based on format
        content: dict[str, str] = {}
        is_image_link = any(
            x in link for x in ["simgad", ".png", ".jpg", ".gif", "googlesyndication.com"]
        )

        if is_image_link:
            format_name = "image"
            content["image_url"] = link
        elif format_name == "text":
            content["preview_url"] = link
            decoded = decode_text_ad(link)
            if decoded:
                content.update(decoded)
        elif format_name == "image":
            content["image_url"] = link
        elif format_name == "video":
            content["video_url"] = link
            # Try to resolve actual video URL
            resolved = self._resolve_video_url(link)
            if resolved != link:
                content["video_url"] = resolved
                content["preview_url"] = link
        else:
            content["preview_url"] = link

        return {
            "advertiser_id": advertiser_id,
            "creative_id": creative_id,
            "format": format_name,
            "last_shown": last_shown,
            "content": content,
        }

    def get_ads(
        self, advertiser_name: str, count: int = 10
    ) -> list[dict[str, Any]]:
        """Search for an advertiser by name and return their ads with decoded content.

        This is a convenience method that combines search + creative fetch + detail lookup.
        """
        # Find advertiser
        suggestions = self.search_suggestions(advertiser_name)
        advertiser_id = ""
        resolved_name = advertiser_name

        for s in suggestions:
            if "1" in s:
                info = s["1"]
                if info.get("1", "").lower() == advertiser_name.lower():
                    advertiser_id = info["2"]
                    resolved_name = info["1"]
                    break
            elif "2" in s:
                domain = s["2"].get("1", "")
                adv = self.search_advertiser_by_domain(domain)
                if adv:
                    advertiser_id = adv["advertiser_id"]
                    resolved_name = adv["name"]
                    break

        # If exact match failed, take the first advertiser result
        if not advertiser_id:
            for s in suggestions:
                if "1" in s:
                    advertiser_id = s["1"]["2"]
                    resolved_name = s["1"]["1"]
                    break

        if not advertiser_id:
            return []

        creative_ids = self.get_creative_ids(advertiser_id, count)
        ads = []
        for cid in creative_ids:
            detail = self.get_ad_detail(advertiser_id, cid)
            detail["advertiser_name"] = resolved_name
            ads.append(detail)
        return ads

    # --- Internal helpers ---

    def _get_ad_count(self, name: str, advertiser_id: str) -> int:
        """Look up ad count for an advertiser via suggestions."""
        suggestions = self.search_suggestions(name)
        for s in suggestions:
            if "1" in s and s["1"].get("2") == advertiser_id:
                try:
                    return int(s["1"]["4"]["2"]["2"])
                except (KeyError, TypeError, ValueError):
                    pass
        return 0

    @staticmethod
    def _extract_ad_link(ad: dict[str, Any]) -> str:
        """Extract the ad preview/content link from the API response."""
        try:
            creatives = ad.get("5", [])
            if not creatives:
                return ""
            creative = creatives[0]
            if "3" in creative and "2" in creative["3"]:
                raw = creative["3"]["2"]
                if 'src="' in raw:
                    return raw.split('src="')[1].split('"')[0]
                elif "'" in raw:
                    return raw.split("'")[1]
                return raw
            for key_path in [("2", "4"), ("1", "4"), ("4",)]:
                obj = creative
                for k in key_path:
                    obj = obj[k]
                return obj
        except (KeyError, IndexError, TypeError):
            pass
        return ""

    def _resolve_video_url(self, link: str) -> str:
        """Resolve a displayads link to its actual video URL."""
        if "displayads" not in link:
            return link
        try:
            resp = requests.post(link, timeout=10)
            txt = next(x for x in resp.text.split("CDATA[") if "googlevideo.com" in x)
            url = str(txt.split("]")[0]).encode("utf-8").decode("unicode_escape")
            return url.encode("utf-8").decode("unicode_escape")
        except Exception:
            return link
