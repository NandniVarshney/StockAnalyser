"""Shared async HTTP client with sensible defaults + retries."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

USER_AGENT = "StockAnalyser/0.1 (+https://github.com/NandniVarshney/StockAnalyser)"


@asynccontextmanager
async def async_client(timeout: float = 30.0) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a configured httpx.AsyncClient."""
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    ) as client:
        yield client


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    backoff_base: float = 1.0,
    **kwargs: object,
) -> httpx.Response:
    """GET with exponential backoff on 429 / 5xx / network errors."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.get(url, **kwargs)  # type: ignore[arg-type]
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last_exc = httpx.HTTPStatusError(
                f"{resp.status_code}", request=resp.request, response=resp
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_exc = e
        await asyncio.sleep(backoff_base * (2**attempt))
    assert last_exc is not None
    raise last_exc
