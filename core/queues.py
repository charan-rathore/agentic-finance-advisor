"""
core/queues.py

Shared async message queues — the "message bus" of this multi-agent system.

Why asyncio.Queue instead of Kafka:
  - Zero infrastructure: no broker, no Docker service, no port config
  - Same conceptual model: producers put(), consumers get()
  - Built into Python stdlib — nothing to install
  - Trivially swappable for Kafka or Redis Streams later

These queues are module-level singletons. All agents import the same
queue instances from here, so they truly share the same channels.

Queue contents (all dicts / JSON-serializable):
  raw_market_queue  → {symbol, price, volume, timestamp}
  raw_news_queue    → {headline, url, body, published_at, source}
  insights_queue    → {user_query, insight_text, sources, sentiment_summary, timestamp}
  raw_india_queue   → {type, prices?, nav_records?, rbi_rates?, news_batches?}
                      type is one of: "india_cycle" | "india_nav" | "india_rbi"
"""

import asyncio

# One queue per data channel — module-level so all agents share the same object
raw_market_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
raw_news_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
insights_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

# Indian market data — separate queue so Indian data never competes for
# processing priority with global data and the shape difference is explicit.
raw_india_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
