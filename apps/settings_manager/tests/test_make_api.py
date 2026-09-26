import httpx
import pytest

from apps.settings_manager.make_api import MakeApiClient, MakeApiError


def test_client_uses_make_region_and_token_without_leaking_credentials(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"organizations": [{"id": 7, "name": "Studio"}]}

    def request(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr(httpx, "request", request)
    client = MakeApiClient("eu1", "make-secret-token")

    assert client.list_organizations() == [{"id": 7, "name": "Studio"}]
    assert seen["url"] == "https://eu1.make.com/api/v2/organizations"
    assert seen["headers"]["Authorization"] == "Token make-secret-token"
    assert "make-secret-token" not in str(seen["params"])


def test_client_rejects_unrecognized_region():
    with pytest.raises(MakeApiError, match="supported Make region"):
        MakeApiClient("attacker.example", "token")


def test_client_redacts_token_on_api_error(monkeypatch):
    class Response:
        status_code = 403

        @staticmethod
        def json():
            return {"message": "make-secret-token is not authorized"}

    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: Response())
    client = MakeApiClient("eu1", "make-secret-token")

    with pytest.raises(MakeApiError) as exc:
        client.list_organizations()

    assert exc.value.status_code == 403
    assert "make-secret-token" not in str(exc.value)


def test_run_scenario_sends_declared_data_and_wait_mode(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"executionId": "execution-1", "status": "1"}

    def request(method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr(httpx, "request", request)
    client = MakeApiClient("us2", "token")

    result = client.run_scenario(42, {"caption": "Pin text"}, wait=True)

    assert result["executionId"] == "execution-1"
    assert seen["url"] == "https://us2.make.com/api/v2/scenarios/42/run"
    assert seen["json"] == {"data": {"caption": "Pin text"}, "responsive": True}


def test_client_marks_transport_timeout(monkeypatch):
    def request(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "request", request)
    client = MakeApiClient("eu1", "token")

    with pytest.raises(MakeApiError) as exc:
        client.list_organizations()

    assert exc.value.timed_out
    assert "token" not in str(exc.value)
