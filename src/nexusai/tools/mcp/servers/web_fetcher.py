"""Built-in Web Fetcher MCP Server providing HTTP requests and content extraction."""

from __future__ import annotations

import argparse
import asyncio
import re
from typing import Any

import httpx

from nexusai.tools.mcp.servers.base import McpServerBase


def _html_to_text(html: str) -> str:
    """Convert HTML content to clean, readable plain text without script/style tags."""
    # Remove script and style elements
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block tags with newlines
    cleaned = re.sub(r"<(p|br|div|h[1-6]|li|tr)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Collapse multiple whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def _extract_title(html: str) -> str:
    """Extract <title> text from HTML if present."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


class WebFetcherMcpServer(McpServerBase):
    """MCP Server providing web fetching, content extraction, and generic HTTP requests."""

    def __init__(self, default_timeout_sec: float = 15.0) -> None:
        super().__init__(
            name="nexus-web-fetcher",
            version="1.0.0",
            description="NexusAI Web Fetcher & HTTP MCP Server",
        )
        self.default_timeout_sec = default_timeout_sec
        self._register_fetcher_tools()

    def _register_fetcher_tools(self) -> None:
        # 1. fetch_url
        self.register_tool(
            name="fetch_url",
            description="Fetch a web page via HTTP GET, convert HTML to clean readable text, and extract metadata.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full HTTP or HTTPS URL to fetch",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters of text content to return (default 10,000)",
                        "default": 10000,
                    },
                },
                "required": ["url"],
            },
            handler=self._handle_fetch_url,
        )

        # 2. http_request
        self.register_tool(
            name="http_request",
            description="Perform a generic HTTP request (GET, POST, PUT, DELETE, PATCH) with optional headers and payload.",
            input_schema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                        "default": "GET",
                    },
                    "url": {
                        "type": "string",
                        "description": "Full target HTTP or HTTPS URL",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP request headers",
                        "default": {},
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional request body string for POST/PUT requests",
                        "default": "",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Request timeout in seconds",
                        "default": 15.0,
                    },
                },
                "required": ["url"],
            },
            handler=self._handle_http_request,
        )

    async def _handle_fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args["url"]).strip()
        max_chars = int(args.get("max_chars", 10000))

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NexusAI-WebFetcher/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.default_timeout_sec
        ) as client:
            resp = await client.get(url, headers=headers)

            content_type = resp.headers.get("content-type", "")
            raw_text = resp.text

            if "html" in content_type.lower():
                title = _extract_title(raw_text)
                extracted_text = _html_to_text(raw_text)
            else:
                title = ""
                extracted_text = raw_text.strip()

            truncated = len(extracted_text) > max_chars
            final_text = extracted_text[:max_chars]

            return {
                "url": str(resp.url),
                "status_code": resp.status_code,
                "title": title,
                "content_type": content_type,
                "text": final_text,
                "total_chars": len(extracted_text),
                "is_truncated": truncated,
            }

    async def _handle_http_request(self, args: dict[str, Any]) -> dict[str, Any]:
        method = str(args.get("method", "GET")).upper()
        url = str(args["url"]).strip()
        headers = dict(args.get("headers", {}))
        body = str(args.get("body", ""))
        timeout = float(args.get("timeout_seconds", self.default_timeout_sec))

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            req_content = body.encode("utf-8") if body else None
            resp = await client.request(method, url, headers=headers, content=req_content)

            resp_text = resp.text
            # Truncate large responses to 20,000 characters
            max_limit = 20000
            truncated = len(resp_text) > max_limit

            return {
                "url": str(resp.url),
                "method": method,
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_text[:max_limit],
                "is_truncated": truncated,
            }


def main() -> None:
    """CLI entry point for running Web Fetcher MCP Server."""
    parser = argparse.ArgumentParser(description="NexusAI Web Fetcher & HTTP MCP Server")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Default HTTP request timeout in seconds (default: 15.0)",
    )
    args = parser.parse_args()

    server = WebFetcherMcpServer(default_timeout_sec=args.timeout)
    server.log("Initialized Web Fetcher MCP Server")
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
