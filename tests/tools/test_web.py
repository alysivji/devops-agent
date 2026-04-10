from typing import Any

import pytest

from agent.run_history import RunHistory, reset_active_run_history, set_active_run_history
from agent.tools.web import http_get, search_web


class StubDDGS:
    def __init__(self, results: list[object] | None = None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error

    def __enter__(self) -> "StubDDGS":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def text(self, query: str, max_results: int) -> list[object]:
        if self.error is not None:
            raise self.error
        return self.results


class TestSearchWeb:
    def test_search_web_rejects_blank_query(self) -> None:
        with pytest.raises(ValueError, match="query must not be empty"):
            search_web("   ")

    def test_search_web_rejects_small_max_results(self) -> None:
        with pytest.raises(ValueError, match="max_results must be between 1 and 10"):
            search_web("ansible apt module", max_results=0)

    def test_search_web_rejects_large_max_results(self) -> None:
        with pytest.raises(ValueError, match="max_results must be between 1 and 10"):
            search_web("ansible apt module", max_results=11)

    def test_search_web_normalizes_results_and_records_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "agent.tools.web.DDGS",
            lambda: StubDDGS(
                results=[
                    {
                        "title": "Ansible apt module",
                        "href": "https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html",
                        "body": "Install packages with apt.",
                        "extra": "ignored",
                    },
                    {
                        "title": "Ansible docs",
                        "url": "https://docs.ansible.com/",
                    },
                ]
            ),
        )
        run_history = RunHistory(prompt="search for apt module docs")
        token = set_active_run_history(run_history)

        try:
            results = search_web("ansible apt module", max_results=1)
        finally:
            reset_active_run_history(token)

        assert results == [
            {
                "title": "Ansible apt module",
                "url": "https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html",
                "snippet": "Install packages with apt.",
            }
        ]
        assert run_history.session.events[-1].kind == "web_search_completed"

    def test_search_web_records_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agent.tools.web.DDGS",
            lambda: StubDDGS(error=RuntimeError("backend down")),
        )
        run_history = RunHistory(prompt="search for docs")
        token = set_active_run_history(run_history)

        try:
            with pytest.raises(RuntimeError, match="web search failed"):
                search_web("ansible docs")
        finally:
            reset_active_run_history(token)

        assert run_history.session.events[-1].kind == "web_search_failed"


class TestHttpGet:
    def test_http_get_rejects_blank_url(self) -> None:
        with pytest.raises(ValueError, match="url must not be empty"):
            http_get("  ")

    def test_http_get_raises_for_invalid_result_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("agent.tools.web.http_request", lambda tool_use: {"status": "success"})

        with pytest.raises(RuntimeError, match="http get failed"):
            http_get("https://docs.ansible.com/")

    def test_http_get_wraps_error_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "agent.tools.web.http_request",
            lambda tool_use: {"status": "error", "content": [{"text": "upstream error"}]},
        )

        with pytest.raises(RuntimeError, match="http get failed"):
            http_get("https://docs.ansible.com/")

    def test_http_get_passes_expected_request_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, Any] = {}

        def fake_http_request(tool_use: dict[str, Any]) -> dict[str, Any]:
            recorded["tool_use"] = tool_use
            return {"status": "success", "content": [{"text": "Status Code: 200"}]}

        monkeypatch.setattr("agent.tools.web.http_request", fake_http_request)

        result = http_get("https://docs.ansible.com/", headers={"Accept": "text/html"})

        assert result == "Status Code: 200"
        assert recorded["tool_use"]["input"] == {
            "method": "GET",
            "url": "https://docs.ansible.com/",
            "headers": {"Accept": "text/html"},
            "allow_redirects": True,
            "convert_to_markdown": True,
        }

    @pytest.mark.vcr
    def test_http_get_fetches_ansible_docs(self) -> None:
        result = http_get(
            "https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html"
        )

        assert "Status Code: 200" in result
        assert "ansible.builtin.apt module" in result

    @pytest.mark.vcr
    def test_http_get_records_run_history_for_success(self) -> None:
        run_history = RunHistory(prompt="fetch apt module docs")
        token = set_active_run_history(run_history)

        try:
            result = http_get(
                "https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html"
            )
        finally:
            reset_active_run_history(token)

        assert "Status Code: 200" in result
        assert run_history.session.events[-1].kind == "http_get_completed"
