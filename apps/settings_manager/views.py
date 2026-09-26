from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.members.decorators import require_permission
from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace

from .make_api import MakeApiClient, MakeApiError
from .models import MakeConnection


@login_required
def settings_index(request):
    return render(request, "settings_manager/index.html")


def _render_make_settings(request, workspace, connection, selected_region):
    organizations = []
    teams = []
    scenarios = []
    if connection:
        client = MakeApiClient(connection.region, connection.api_token)
        try:
            organizations = client.list_organizations()
            if connection.organization_id:
                teams = client.list_teams(connection.organization_id)
            if connection.team_id:
                scenarios = client.list_scenarios(connection.team_id)
        except MakeApiError as exc:
            messages.error(request, str(exc))

    selected_ids = {str(scenario_id) for scenario_id in (connection.allowed_scenario_ids if connection else [])}
    for scenario in scenarios:
        scenario["selected"] = str(scenario.get("id", "")) in selected_ids

    return render(
        request,
        "workspaces/make_settings.html",
        {
            "workspace": workspace,
            "settings_active": "make",
            "connection": connection,
            "regions": MakeConnection.Region.choices,
            "selected_region": selected_region,
            "organizations": organizations,
            "teams": teams,
            "scenarios": scenarios,
        },
    )


@login_required
@require_permission("manage_workspace_settings")
@require_http_methods(["GET", "POST"])
@ratelimit(key="user", rate="20/m", method="POST", block=True)
def make_integration(request, workspace_id):
    workspace = get_object_or_404(Workspace, id=workspace_id)
    if not WorkspaceMembership.objects.filter(user=request.user, workspace=workspace).exists():
        raise Http404

    connection = MakeConnection.objects.filter(workspace=workspace).first()
    selected_region = request.POST.get("region") or (connection.region if connection else "eu1")

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "connect":
            entered_token = request.POST.get("api_token", "").strip()
            token = entered_token or (connection.api_token if connection else "")
            if not token:
                messages.error(request, "Enter a Make API token.")
                return _render_make_settings(request, workspace, connection, selected_region)

            try:
                client = MakeApiClient(selected_region, token)
                organizations = client.list_organizations()
            except MakeApiError as exc:
                messages.error(request, str(exc))
                return _render_make_settings(request, workspace, connection, selected_region)

            if not organizations:
                messages.error(request, "This Make API token has no accessible organizations.")
                return _render_make_settings(request, workspace, connection, selected_region)

            token_changed = connection is None or bool(entered_token and entered_token != connection.api_token)
            connection, _ = MakeConnection.objects.update_or_create(
                workspace=workspace,
                defaults={
                    "api_token": token,
                    "region": selected_region,
                    **(
                        {"organization_id": None, "team_id": None, "allowed_scenario_ids": []}
                        if token_changed or (connection and selected_region != connection.region)
                        else {}
                    ),
                },
            )
            messages.success(
                request, "Make account connected. Select the organization, team, and scenarios to expose to MCP."
            )
            return redirect("workspaces:make_settings", workspace_id=workspace.id)

        if action == "disconnect":
            if connection:
                connection.delete()
            messages.success(request, "Make.com disconnected from this workspace.")
            return redirect("workspaces:make_settings", workspace_id=workspace.id)

        if not connection:
            messages.error(request, "Connect a Make account first.")
            return redirect("workspaces:make_settings", workspace_id=workspace.id)

        client = MakeApiClient(connection.region, connection.api_token)
        try:
            if action == "organization":
                organization_id = int(request.POST.get("organization_id", ""))
                available = {int(item["id"]) for item in client.list_organizations() if item.get("id") is not None}
                if organization_id not in available:
                    raise ValueError("Choose an organization returned by Make.")
                connection.organization_id = organization_id
                connection.team_id = None
                connection.allowed_scenario_ids = []
                connection.save(update_fields=["organization_id", "team_id", "allowed_scenario_ids", "updated_at"])
                messages.success(request, "Make organization selected.")
            elif action == "team":
                if not connection.organization_id:
                    raise ValueError("Select a Make organization first.")
                team_id = int(request.POST.get("team_id", ""))
                available = {
                    int(item["id"])
                    for item in client.list_teams(connection.organization_id)
                    if item.get("id") is not None
                }
                if team_id not in available:
                    raise ValueError("Choose a team returned by Make.")
                connection.team_id = team_id
                connection.allowed_scenario_ids = []
                connection.save(update_fields=["team_id", "allowed_scenario_ids", "updated_at"])
                messages.success(request, "Make team selected.")
            elif action == "scenarios":
                if not connection.team_id:
                    raise ValueError("Select a Make team first.")
                requested = {int(value) for value in request.POST.getlist("scenario_ids")}
                available = {
                    int(item["id"]) for item in client.list_scenarios(connection.team_id) if item.get("id") is not None
                }
                if not requested.issubset(available):
                    raise ValueError("Only scenarios from the selected Make team can be enabled.")
                connection.allowed_scenario_ids = sorted(requested)
                connection.save(update_fields=["allowed_scenario_ids", "updated_at"])
                messages.success(request, "MCP scenario access updated.")
            else:
                messages.error(request, "Unknown Make integration action.")
        except (MakeApiError, TypeError, ValueError) as exc:
            messages.error(request, str(exc) or "Choose a valid Make organization, team, or scenario.")

        return redirect("workspaces:make_settings", workspace_id=workspace.id)

    return _render_make_settings(request, workspace, connection, selected_region)
