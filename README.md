# Google Ads Transparency MCP Server

An MCP server that lets AI assistants look up any advertiser's Google ads. Search by domain or company name, retrieve ad creatives, and decode text ad content — all from Google's [Ads Transparency Center](https://adstransparency.google.com/).

**No API key. No paid service. No browser required.**

Google has no official API for their Ads Transparency Center. The only open-source option was an [abandoned Python package](https://github.com/faniAhmed/GoogleAdsTransparencyScraper) (last commit July 2023, broken domain search, crashed on image ads). Paid alternatives start at $75/mo. This project fixes the scraper and wraps it as an MCP server so any AI assistant can query Google's ad database directly.

## Tools

| Tool | Description |
|------|-------------|
| `search_advertiser_by_domain` | Find an advertiser by website domain (e.g. `nike.com`) |
| `search_advertisers` | Search advertisers by keyword or company name |
| `get_ads` | Get ads for an advertiser with decoded content |
| `get_ad_detail` | Get full details for a specific ad creative |

## Install

```bash
# With uvx (recommended)
uvx google-ads-transparency-mcp

# With pip
pip install google-ads-transparency-mcp
```

## Configure

### Claude Code

```bash
claude mcp add google-ads-transparency -- uvx google-ads-transparency-mcp
```

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-ads-transparency": {
      "command": "uvx",
      "args": ["google-ads-transparency-mcp"]
    }
  }
}
```

### Cursor / VS Code

Add to your MCP settings:

```json
{
  "mcpServers": {
    "google-ads-transparency": {
      "command": "uvx",
      "args": ["google-ads-transparency-mcp"]
    }
  }
}
```

## Example Usage

Once connected, ask your AI assistant things like:

- *"What ads is nike.com running?"*
- *"Search for crypto exchange advertisers on Google"*
- *"Get the last 5 ads from Coinbase"*
- *"Look up ad details for advertiser AR05099026886533578753"*

### Example: Domain Search

```
> search_advertiser_by_domain("nike.com")

{
  "advertiser_id": "AR14188379519798214657",
  "name": "Nike, Inc.",
  "ad_count": 1842
}
```

### Example: Get Ads with Decoded Text Content

```
> get_ads("Coinbase", count=1)

[
  {
    "advertiser_id": "AR09076382774528",
    "creative_id": "CR10813648716908961793",
    "format": "text",
    "last_shown": "2025-01-15",
    "advertiser_name": "Coinbase",
    "content": {
      "preview_url": "https://ads-rendering-prod.corp.google.com/search?...",
      "headline": "Most Trusted Crypto Exchange",
      "description": "Buy, Sell & Trade Bitcoin, Ethereum & More...",
      "destination_url": "coinbase.com"
    }
  }
]
```

## How It Works

This server reverse-engineers Google's internal RPC endpoints:

| Endpoint | Purpose |
|----------|---------|
| `SearchService/SearchSuggestions` | Keyword/domain search |
| `SearchService/SearchCreatives` | Get ad creative IDs by advertiser |
| `LookupService/GetCreativeById` | Get individual ad details |

Text/search ads have their content encoded as base64 in iframe preview URLs. The server decodes these to extract headlines, descriptions, and destination URLs.

## Use as a Python Library

```python
from google_ads_transparency_mcp import GoogleAdsTransparency

client = GoogleAdsTransparency()

# Search by domain
advertiser = client.search_advertiser_by_domain("nike.com")
print(advertiser)  # {"advertiser_id": "...", "name": "Nike, Inc.", "ad_count": 1842}

# Get ads with decoded content
ads = client.get_ads("Coinbase", count=5)
for ad in ads:
    print(ad["format"], ad["content"])

# Region-specific search
client_uk = GoogleAdsTransparency(region="GB")
```

## Supported Regions

Pass a two-letter country code to filter by region. Use `"anywhere"` (default) for global results. All [240+ regions](https://adstransparency.google.com/) from Google's Ads Transparency Center are supported.

## Credits

Based on [GoogleAdsTransparencyScraper](https://github.com/faniAhmed/GoogleAdsTransparencyScraper) by Farhan Ahmed. Forked and fixed by [Sam Town](https://samuel.town) — domain search, image ad parsing, text ad decoding, error handling, and MCP server.

## License

MIT
