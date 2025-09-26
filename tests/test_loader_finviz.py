from premarket import loader_finviz


def test_http_get_falls_back_to_urllib(monkeypatch):
    def fail_with_stub(_url: str) -> str:
        raise loader_finviz.requests.RequestException(
            "Network access disabled in test environment"
        )

    def succeed_with_urllib(url: str) -> str:
        assert url == "https://example.com/export"
        return "ok"

    monkeypatch.setattr(loader_finviz, "_fetch_with_requests", fail_with_stub)
    monkeypatch.setattr(loader_finviz, "_fetch_with_urllib", succeed_with_urllib)

    result = loader_finviz._http_get("https://example.com/export")

    assert result == "ok"
