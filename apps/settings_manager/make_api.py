"""Small Make API client used by the workspace integration and MCP tools."""

from __future__ import annotations

from typing import Any

import httpx

REGION_BASE_URLS = {
    "eu1": "https://eu1.make.com/api/v2",
    "eu2": "https://eu2.make.com/api/v2",
    "us1": "https://us1.make.com/api/v2",
    "us2": "https://us2.make.com/api/v2",
    "eu1-celonis": "https://eu1.make.celonis.com/api/v2",
    "us1-celonis": "https://us1.make.celonis.com/api/v2",
}


class MakeApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, timed_out: bool = False):
        self.status_code = status_code
        self.timed_out = timed_out
        super().__init__(message)


class MakeApiClient:
    def __init__(self, region: str, api_token: str):
        try:
            self.base_url = REGION_BASE_URLS[region]
        except KeyError as exc:
            raise MakeApiError("Choose a supported Make region.") from exc
        if not api_token.strip():
            raise MakeApiError("Enter a Make API token.")
        self.api_token = api_token.strip()

    def _request(self, method: str, path: str, *, params=None, body=None, timeout: float = 12) -> dict:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Token {self.api_token}", "Accept": "application/json"},
                params=params,
                json=body,
                timeout=timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise MakeApiError("Make API request timed out.", timed_out=True) from None
        except httpx.HTTPError:
            raise MakeApiError("Could not reach the Make API.") from None

        if response.status_code >= 400:
            if response.status_code in (408, 504):
                message = "Make API request timed out."
            elif response.status_code in (401, 403):
                message = "Make rejected the token or its required API scopes."
            elif response.status_code == 429:
                message = "Make API rate limit reached; try again later."
            else:
                message = f"Make API request failed (HTTP {response.status_code})."
            raise MakeApiError(
                message,
                status_code=response.status_code,
                timed_out=response.status_code in (408, 504),
            )

        try:
            payload = response.json()
        except ValueError:
            raise MakeApiError("Make returned an invalid API response.", status_code=response.status_code) from None
        if not isinstance(payload, dict):
            raise MakeApiError("Make returned an invalid API response.", status_code=response.status_code)
        return payload

    @staticmethod
    def _items(payload: dict, key: str) -> list[dict]:
        items = payload.get(key) or []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def list_organizations(self) -> list[dict]:
        return self._items(self._request("GET", "/organizations"), "organizations")

    def list_teams(self, organization_id: int) -> list[dict]:
        payload = self._request("GET", "/teams", params={"organizationId": organization_id})
        return self._items(payload, "teams")

    def list_scenarios(self, team_id: int) -> list[dict]:
        payload = self._request(
            "GET",
            "/scenarios",
            params={
                "teamId": team_id,
                "type": "scenario",
                "pg[limit]": 10000,
                "cols[]": ["id", "name", "isActive", "scheduling"],
            },
        )
        return self._items(payload, "scenarios")

    def get_scenario_interface(self, scenario_id: int) -> dict:
        payload = self._request("GET", f"/scenarios/{scenario_id}/interface")
        interface = payload.get("interface") or {}
        return interface if isinstance(interface, dict) else {}

    def run_scenario(self, scenario_id: int, data: dict[str, Any], *, wait: bool = False) -> dict:
        return self._request(
            "POST",
            f"/scenarios/{scenario_id}/run",
            body={"data": data, "responsive": wait},
            timeout=45 if wait else 12,
        )
