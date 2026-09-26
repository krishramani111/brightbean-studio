import json
from types import SimpleNamespace

import pytest

from apps.mcp.handlers import _list_make_scenarios, _run_make_scenario
from apps.mcp.protocol import INVALID_PARAMS, JsonRpcError
from apps.mcp.tools import get_tool
from apps.organizations.models import Organization
from apps.settings_manager.make_api import MakeApiClient, MakeApiError
from apps.settings_manager.models import MakeConnection
from apps.workspaces.models import Workspace


@pytest.fixture
def workspace(db):
    organization = Organization.objects.create(name="Make MCP Org")
    return Workspace.objects.create(name="Make MCP Workspace", organization=organization)


@pytest.fixture
def make_connection(workspace):
    return MakeConnection.objects.create(
        workspace=workspace,
        api_token="test-token",
        region="eu1",
        organization_id=1,
        team_id=2,
        allowed_scenario_ids=[11],
    )


@pytest.fixture
def context(workspace):
    return {
        "workspace": workspace,
        "membership": SimpleNamespace(effective_permissions={"publish_directly": True}),
    }


def _payload(result):
    return json.loads(result["content"][0]["text"])


def test_make_tools_are_registered():
    assert get_tool("list_make_scenarios") is not None
    assert get_tool("run_make_scenario") is not None


def test_list_make_scenarios_only_returns_enabled_scenarios(monkeypatch, make_connection, context):
    monkeypatch.setattr(
        MakeApiClient,
        "list_scenarios",
        lambda self, team_id: [
            {"id": 11, "name": "Pinterest pin", "isActive": True},
            {"id": 22, "name": "Other workflow", "isActive": True},
        ],
    )
    monkeypatch.setattr(
        MakeApiClient,
        "get_scenario_interface",
        lambda self, scenario_id: {"input": [{"name": "caption", "type": "text", "required": True}]},
    )

    result = _payload(_list_make_scenarios({}, context))

    assert [scenario["scenario_id"] for scenario in result["scenarios"]] == [11]
    assert result["scenarios"][0]["inputs"][0]["name"] == "caption"


def test_run_make_scenario_passes_input_and_wait_choice(monkeypatch, make_connection, context):
    seen = {}
    monkeypatch.setattr(
        MakeApiClient,
        "get_scenario_interface",
        lambda self, scenario_id: {"input": [{"name": "caption", "required": True}]},
    )

    def run_scenario(self, scenario_id, data, *, wait):
        seen.update(scenario_id=scenario_id, data=data, wait=wait)
        return {"executionId": "run-1"}

    monkeypatch.setattr(MakeApiClient, "run_scenario", run_scenario)

    result = _payload(
        _run_make_scenario(
            {"scenario_id": 11, "data": {"caption": "Pin text"}, "wait_for_completion": True},
            context,
        )
    )

    assert seen == {"scenario_id": 11, "data": {"caption": "Pin text"}, "wait": True}
    assert result == {"scenario_id": 11, "executionId": "run-1"}


def test_run_rejects_unselected_scenario(monkeypatch, make_connection, context):
    monkeypatch.setattr(MakeApiClient, "get_scenario_interface", lambda self, scenario_id: {"input": []})

    with pytest.raises(JsonRpcError) as exc:
        _run_make_scenario({"scenario_id": 22}, context)

    assert exc.value.code == INVALID_PARAMS
    assert "not enabled" in exc.value.message


def test_run_validates_declared_required_and_unknown_inputs(monkeypatch, make_connection, context):
    monkeypatch.setattr(
        MakeApiClient,
        "get_scenario_interface",
        lambda self, scenario_id: {"input": [{"name": "caption", "required": True}]},
    )

    with pytest.raises(JsonRpcError, match="Missing required Make scenario inputs"):
        _run_make_scenario({"scenario_id": 11}, context)
    with pytest.raises(JsonRpcError, match="Unknown Make scenario inputs"):
        _run_make_scenario({"scenario_id": 11, "data": {"caption": "x", "wrong": 1}}, context)


def test_list_and_run_require_publish_permission(monkeypatch, make_connection, context):
    context["membership"] = SimpleNamespace(effective_permissions={"publish_directly": False})

    with pytest.raises(JsonRpcError, match="Permission denied: publish_directly"):
        _list_make_scenarios({}, context)
    with pytest.raises(JsonRpcError, match="Permission denied: publish_directly"):
        _run_make_scenario({"scenario_id": 11}, context)


def test_make_timeout_is_unknown_and_not_retryable(monkeypatch, make_connection, context):
    monkeypatch.setattr(MakeApiClient, "get_scenario_interface", lambda self, scenario_id: {"input": []})

    def timeout(*args, **kwargs):
        raise MakeApiError("Make API request timed out.", timed_out=True)

    monkeypatch.setattr(MakeApiClient, "run_scenario", timeout)

    result = _payload(
        _run_make_scenario(
            {"scenario_id": 11, "wait_for_completion": True},
            context,
        )
    )

    assert result["status"] == "unknown"
    assert result["retry_safe"] is False


def test_missing_make_connection_has_actionable_error(workspace):
    context = {
        "workspace": workspace,
        "membership": SimpleNamespace(effective_permissions={"publish_directly": True}),
    }

    with pytest.raises(JsonRpcError, match="Connect Make.com in Workspace Settings") as exc:
        _list_make_scenarios({}, context)
    assert exc.value.code == INVALID_PARAMS


def test_make_connection_is_not_visible_across_workspaces(db, context):
    other_organization = Organization.objects.create(name="Other Make Org")
    other_workspace = Workspace.objects.create(name="Other Make Workspace", organization=other_organization)
    MakeConnection.objects.create(
        workspace=other_workspace,
        api_token="other-token",
        region="eu1",
        organization_id=3,
        team_id=4,
        allowed_scenario_ids=[22],
    )

    with pytest.raises(JsonRpcError, match="Connect Make.com in Workspace Settings"):
        _list_make_scenarios({}, context)
