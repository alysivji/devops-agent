from collections.abc import Mapping
from typing import TypedDict

from ddgs import DDGS
from strands import tool
from strands_tools.http_request import http_request

from ..history import record_event

MAX_SEARCH_RESULTS = 10
RESULT_PREVIEW_LENGTH = 200


class WebSearchResult(TypedDict):
    title: str
    url: str
    snippet: str


@tool
def search_web(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """Search the web and return compact result snippets."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if max_results < 1 or max_results > MAX_SEARCH_RESULTS:
        raise ValueError(f"max_results must be between 1 and {MAX_SEARCH_RESULTS}")

    record_event(
        kind="web_search_started",
        status="started",
        what="Started web search.",
        why="Fetch current documentation or examples to improve playbook generation.",
        details={"query": normalized_query, "max_results": max_results},
    )

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(normalized_query, max_results=max_results))
    except Exception as exc:
        record_event(
            kind="web_search_failed",
            status="failed",
            what="Web search failed.",
            why="The search backend did not return usable search results.",
            details={
                "query": normalized_query,
                "max_results": max_results,
                "error": str(exc),
                "exception_type": exc.__class__.__name__,
            },
        )
        raise RuntimeError("web search failed") from exc

    results = [_normalize_search_result(item) for item in raw_results[:max_results]]
    if not all(result["url"] for result in results):
        record_event(
            kind="web_search_failed",
            status="failed",
            what="Web search returned unusable results.",
            why="Each search result must include a URL so the agent can inspect sources.",
            details={"query": normalized_query, "max_results": max_results},
        )
        raise RuntimeError("web search returned unusable results")

    record_event(
        kind="web_search_completed",
        status="completed",
        what="Completed web search.",
        why="Return compact search results so the generator can choose pages to inspect.",
        details={
            "query": normalized_query,
            "max_results": max_results,
            "result_count": len(results),
            "urls": [result["url"] for result in results],
        },
    )
    return results


@tool
def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    convert_html_to_markdown: bool = True,
) -> str:
    """Fetch a URL with GET only and return concatenated text blocks."""
    normalized_url = url.strip()
    if not normalized_url:
        raise ValueError("url must not be empty")

    record_event(
        kind="http_get_started",
        status="started",
        what=f"Started HTTP GET for `{normalized_url}`.",
        why="Read documentation or example pages without allowing mutating requests.",
        details={
            "url": normalized_url,
            "convert_html_to_markdown": convert_html_to_markdown,
        },
    )

    tool_use = {
        "toolUseId": "http_get",
        "input": {
            "method": "GET",
            "url": normalized_url,
            "headers": headers or {},
            "allow_redirects": True,
            "convert_to_markdown": convert_html_to_markdown,
        },
    }

    try:
        result = http_request(tool_use)
        text = _extract_http_text(result)
    except Exception as exc:
        record_event(
            kind="http_get_failed",
            status="failed",
            what=f"HTTP GET failed for `{normalized_url}`.",
            why="The documentation fetch did not return a usable success response.",
            details={"url": normalized_url, "error": str(exc)},
        )
        raise RuntimeError(f"http get failed for {normalized_url}") from exc

    record_event(
        kind="http_get_completed",
        status="completed",
        what=f"Completed HTTP GET for `{normalized_url}`.",
        why="Return page content so the generator can extract implementation details.",
        details={"url": normalized_url, "response_preview": _preview_text(text)},
    )
    return text


def _normalize_search_result(item: object) -> WebSearchResult:
    if not isinstance(item, Mapping):
        raise RuntimeError("web search returned unusable results")

    title = item.get("title")
    url = item.get("href") or item.get("url")
    snippet = item.get("body") or item.get("snippet")
    return {
        "title": title if isinstance(title, str) else "",
        "url": url if isinstance(url, str) else "",
        "snippet": snippet if isinstance(snippet, str) else "",
    }


def _extract_http_text(result: object) -> str:
    if not isinstance(result, Mapping):
        raise RuntimeError("http request returned an invalid result")

    status = result.get("status")
    content = result.get("content")
    if status != "success":
        raise RuntimeError(_extract_error_text(content))
    if not isinstance(content, list):
        raise RuntimeError("http request returned invalid content")

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            text_parts.append(text)

    if not text_parts:
        raise RuntimeError("http request returned no text content")
    return "\n".join(text_parts)


def _extract_error_text(content: object) -> str:
    if isinstance(content, list):
        for block in content:
            if isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str) and text:
                    return text
    return "http request failed"


def _preview_text(text: str) -> str:
    if len(text) <= RESULT_PREVIEW_LENGTH:
        return text
    return f"{text[: RESULT_PREVIEW_LENGTH - 3]}..."
