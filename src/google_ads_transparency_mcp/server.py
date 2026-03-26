"""MCP server for the Google Ads Transparency Center."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .scraper import GoogleAdsTransparency

mcp = FastMCP(
    "Google Ads Transparency",
    instructions=(
        "Look up any advertiser's Google ads — search by domain or keyword, "
        "retrieve ad creatives, and decode text ad content. "
        "No API key required."
    ),
)

_client: GoogleAdsTransparency | None = None


def _get_client() -> GoogleAdsTransparency:
    global _client
    if _client is None:
        _client = GoogleAdsTransparency()
    return _client


@mcp.tool()
def search_advertiser_by_domain(domain: str) -> dict | None:
    """Find an advertiser by their website domain.

    Args:
        domain: The domain to search for (e.g. "nike.com", "coinbase.com")

    Returns:
        Advertiser info with advertiser_id, name, and ad_count — or null if not found.
    """
    return _get_client().search_advertiser_by_domain(domain)


@mcp.tool()
def search_advertisers(query: str) -> list[dict]:
    """Search for advertisers by keyword or company name.

    Args:
        query: Search query (e.g. "Nike", "Coinbase", "crypto exchange")

    Returns:
        List of matching advertisers with advertiser_id, name, region, and ad_count.
    """
    return _get_client().search_advertisers(query)


@mcp.tool()
def get_ads(advertiser_name: str, count: int = 10) -> list[dict]:
    """Get ads for an advertiser with decoded content.

    Searches for the advertiser by name, fetches their ad creatives, and returns
    full details including decoded text ad content (headline, description, destination URL).

    Args:
        advertiser_name: The advertiser's name (e.g. "Nike, Inc.", "Coinbase")
        count: Number of ads to retrieve (default 10, max 100)

    Returns:
        List of ad details with format, date, and content fields.
    """
    count = max(1, min(count, 100))
    return _get_client().get_ads(advertiser_name, count)


@mcp.tool()
def get_ad_detail(advertiser_id: str, creative_id: str) -> dict:
    """Get full details for a specific ad creative.

    Args:
        advertiser_id: The advertiser's ID (e.g. "AR05099026886533578753")
        creative_id: The creative/ad ID (e.g. "CR10813648716908961793")

    Returns:
        Ad detail with format (text/image/video), last_shown date, and content.
        For text ads, content includes headline, description, and destination_url.
        For image ads, content includes image_url.
        For video ads, content includes video_url.
    """
    return _get_client().get_ad_detail(advertiser_id, creative_id)
