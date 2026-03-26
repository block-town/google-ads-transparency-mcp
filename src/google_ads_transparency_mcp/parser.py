"""Decode text ad content from Google Ads Transparency iframe preview URLs.

Google encodes search/text ad creatives as base64 in the `ad=` parameter of iframe
src URLs like:
    https://ads-rendering-prod.corp.google.com/search?...&ad=ev0BQjZNb3N0IFRy...

The decoded bytes contain ad copy (headline, description, destination URL) wrapped
in a protobuf-like binary framing. This module extracts the readable fields.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, urlparse


def decode_text_ad(iframe_url: str) -> dict[str, str] | None:
    """Extract headline, description, and destination URL from an iframe preview URL.

    Returns None if the URL doesn't contain decodable ad data.
    """
    ad_param = _extract_ad_param(iframe_url)
    if not ad_param:
        return None

    try:
        raw = base64.b64decode(ad_param + "==")  # pad generously
    except Exception:
        return None

    return _parse_ad_bytes(raw)


def _extract_ad_param(url: str) -> str | None:
    """Pull the `ad=` query parameter from a URL."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        values = params.get("ad")
        if values:
            return values[0]
    except Exception:
        pass

    # Fallback: regex for ad= in case URL is malformed
    match = re.search(r"[?&]ad=([A-Za-z0-9_+/=-]+)", url)
    return match.group(1) if match else None


def _parse_ad_bytes(data: bytes) -> dict[str, str]:
    """Extract readable text fields from the decoded protobuf-like binary.

    The binary format contains length-prefixed UTF-8 strings with single-byte
    type/field tags before them. We extract all printable strings and map them
    to headline, description, and destination URL by position and content heuristics.
    """
    strings = _extract_strings(data)

    headline = ""
    description = ""
    destination_url = ""

    for s in strings:
        s_stripped = s.strip()
        if not s_stripped:
            continue
        # URL detection
        if _looks_like_url(s_stripped):
            if not destination_url:
                destination_url = s_stripped
        elif not headline:
            headline = s_stripped
        elif not description:
            description = s_stripped

    return {
        "headline": headline,
        "description": description,
        "destination_url": destination_url,
    }


def _extract_strings(data: bytes) -> list[str]:
    """Extract length-prefixed strings from protobuf-like binary data.

    Walks the byte stream looking for sequences that decode as readable UTF-8.
    Uses a combination of protobuf wire-type-2 (length-delimited) parsing and
    fallback regex extraction.
    """
    strings: list[str] = []

    # Strategy 1: walk protobuf-style length-delimited fields
    i = 0
    while i < len(data) - 1:
        byte = data[i]
        # Check for wire type 2 (length-delimited): low 3 bits == 0b010
        if (byte & 0x07) == 0x02:
            i += 1
            if i >= len(data):
                break
            length = data[i]
            i += 1
            if length > 0 and i + length <= len(data):
                chunk = data[i : i + length]
                try:
                    text = chunk.decode("utf-8")
                    if _is_readable(text) and len(text) >= 3:
                        strings.append(text)
                except UnicodeDecodeError:
                    pass
                i += length
            else:
                # length didn't make sense, skip
                pass
        else:
            i += 1

    # Strategy 2: fallback regex on the raw bytes for any missed strings
    # Look for runs of printable ASCII/UTF-8 at least 5 chars long
    if len(strings) < 2:
        for match in re.finditer(rb"[\x20-\x7e]{5,}", data):
            text = match.group().decode("ascii", errors="ignore").strip()
            if text and text not in strings and _is_readable(text):
                strings.append(text)

    return strings


def _is_readable(text: str) -> bool:
    """Check if a string looks like human-readable ad copy or a URL."""
    if len(text) < 3:
        return False
    # Reject strings that are mostly non-printable or control characters
    printable_count = sum(1 for c in text if c.isprintable())
    return printable_count / len(text) > 0.8


def _looks_like_url(text: str) -> bool:
    """Heuristic: does this string look like a URL or domain?"""
    return bool(
        text.startswith(("http://", "https://", "www."))
        or re.match(r"^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", text)
    )
