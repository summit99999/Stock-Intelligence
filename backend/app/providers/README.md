Keep vendor integrations behind provider adapters; never scrape NSE/BSE pages.
Yahoo Finance/yfinance can be useful for personal historical research where its terms
and data availability permit, but it is unofficial and not an exchange-authorized
real-time feed. Store provider, retrieved_at, interval and delayed/live status.
Upstox is an optional connector: use its documented OAuth flow, keep tokens in
environment variables, and verify API permissions, limits and exchange-data terms.
A free API does not automatically grant redistribution rights.
