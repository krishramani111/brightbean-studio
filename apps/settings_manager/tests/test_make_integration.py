import pytest
from django.db import connection as db_connection
from django.urls import reverse
from django.utils import timezone

from apps.settings_manager.make_api import MakeApiClient
from apps.settings_manager.models import MakeConnection
from apps.workspaces.models import Workspace


@pytest.fixture
def owner_setup(db):
    from apps.accounts.models import User
    from apps.members.models import OrgMembership, WorkspaceMembership
    from apps.organizations.models import Organization

    user = User.objects.create_user(
        email="make-owner@example.com",
        password="testpass123",
        name="Make Owner",
        tos_accepted_at=timezone.now(),
    )
    organization = Organization.objects.create(name="Make Org")
    workspace = Workspace.objects.create(name="Make Workspace", organization=organization)
    OrgMembership.objects.create(user=user, organization=organization, org_role=OrgMembership.OrgRole.OWNER)
    WorkspaceMembership.objects.create(
        user=user,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )
    return user, workspace


def test_connect_verifies_and_encrypts_token(client, monkeypatch, owner_setup):
    user, workspace = owner_setup
    client.force_login(user)
    monkeypatch.setattr(MakeApiClient, "list_organizations", lambda self: [{"id": 7, "name": "Studio"}])
    url = reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id})

    page = client.get(url)
    assert page.status_code == 200
    assert b"Make.com integration" in page.content

    response = client.post(
        url,
        {"action": "connect", "region": "eu1", "api_token": "make-secret-token"},
    )

    assert response.status_code == 302
    make_connection = MakeConnection.objects.get(workspace=workspace)
    assert make_connection.api_token == "make-secret-token"
    with db_connection.cursor() as cursor:
        cursor.execute(f"SELECT api_token FROM {db_connection.ops.quote_name(MakeConnection._meta.db_table)}")
        stored_value = cursor.fetchone()[0]
    assert stored_value != "make-secret-token"


def test_invalid_token_does_not_create_connection(client, monkeypatch, owner_setup):
    user, workspace = owner_setup
    client.force_login(user)

    def reject(_self):
        from apps.settings_manager.make_api import MakeApiError

        raise MakeApiError("Make rejected the token or its required API scopes.", status_code=403)

    monkeypatch.setattr(MakeApiClient, "list_organizations", reject)
    response = client.post(
        reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id}),
        {"action": "connect", "region": "eu1", "api_token": "invalid-token"},
    )

    assert response.status_code == 200
    assert not MakeConnection.objects.filter(workspace=workspace).exists()
    assert b"required API scopes" in response.content
    assert b"invalid-token" not in response.content


def test_replacing_token_clears_previous_scenario_allowlist(client, monkeypatch, owner_setup):
    user, workspace = owner_setup
    client.force_login(user)
    MakeConnection.objects.create(
        workspace=workspace,
        api_token="old-token",
        region="eu1",
        organization_id=7,
        team_id=8,
        allowed_scenario_ids=[9],
    )
    monkeypatch.setattr(MakeApiClient, "list_organizations", lambda self: [{"id": 7, "name": "Studio"}])

    response = client.post(
        reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id}),
        {"action": "connect", "region": "eu1", "api_token": "new-token"},
    )

    assert response.status_code == 302
    make_connection = MakeConnection.objects.get(workspace=workspace)
    assert make_connection.api_token == "new-token"
    assert make_connection.organization_id is None
    assert make_connection.team_id is None
    assert make_connection.allowed_scenario_ids == []


def test_workspace_owner_can_select_org_team_and_scenarios(client, monkeypatch, owner_setup):
    user, workspace = owner_setup
    client.force_login(user)
    MakeConnection.objects.create(workspace=workspace, api_token="encrypted", region="eu1")
    monkeypatch.setattr(MakeApiClient, "list_organizations", lambda self: [{"id": 7, "name": "Studio"}])
    monkeypatch.setattr(MakeApiClient, "list_teams", lambda self, organization_id: [{"id": 8, "name": "Social"}])
    monkeypatch.setattr(
        MakeApiClient,
        "list_scenarios",
        lambda self, team_id: [{"id": 9, "name": "Pinterest pin"}] if team_id == 8 else [],
    )
    url = reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id})

    assert client.post(url, {"action": "organization", "organization_id": "7"}).status_code == 302
    assert client.post(url, {"action": "team", "team_id": "8"}).status_code == 302
    assert client.post(url, {"action": "scenarios", "scenario_ids": ["9"]}).status_code == 302

    make_connection = MakeConnection.objects.get(workspace=workspace)
    assert make_connection.organization_id == 7
    assert make_connection.team_id == 8
    assert make_connection.allowed_scenario_ids == [9]


def test_workspace_owner_cannot_enable_scenario_from_another_team(client, monkeypatch, owner_setup):
    user, workspace = owner_setup
    client.force_login(user)
    MakeConnection.objects.create(
        workspace=workspace,
        api_token="encrypted",
        region="eu1",
        organization_id=7,
        team_id=8,
    )
    monkeypatch.setattr(MakeApiClient, "list_scenarios", lambda self, team_id: [{"id": 9, "name": "Allowed"}])

    response = client.post(
        reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id}),
        {"action": "scenarios", "scenario_ids": ["10"]},
    )

    assert response.status_code == 302
    assert MakeConnection.objects.get(workspace=workspace).allowed_scenario_ids == []


def test_member_without_settings_permission_cannot_manage_make_connection(client, owner_setup):
    from apps.accounts.models import User
    from apps.members.models import WorkspaceMembership

    _, workspace = owner_setup
    manager = User.objects.create_user(
        email="make-manager@example.com",
        password="testpass123",
        name="Make Manager",
        tos_accepted_at=timezone.now(),
    )
    WorkspaceMembership.objects.create(
        user=manager,
        workspace=workspace,
        workspace_role=WorkspaceMembership.WorkspaceRole.MANAGER,
    )
    client.force_login(manager)

    response = client.get(reverse("workspaces:make_settings", kwargs={"workspace_id": workspace.id}))

    assert response.status_code == 403
