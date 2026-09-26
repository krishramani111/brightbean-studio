import uuid

from django.db import models

from apps.common.encryption import EncryptedTextField
from apps.common.managers import OrgScopedManager


class OrgSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    key = models.CharField(max_length=255)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrgScopedManager()

    class Meta:
        db_table = "settings_org_setting"
        unique_together = [("organization", "key")]

    def __str__(self):
        return f"{self.organization.name}: {self.key}"


class WorkspaceSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    key = models.CharField(max_length=255)
    value = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "settings_workspace_setting"
        unique_together = [("workspace", "key")]

    def __str__(self):
        return f"{self.workspace.name}: {self.key}"


class MakeConnection(models.Model):
    class Region(models.TextChoices):
        EU1 = "eu1", "EU1"
        EU2 = "eu2", "EU2"
        US1 = "us1", "US1"
        US2 = "us2", "US2"
        EU1_CELONIS = "eu1-celonis", "EU1 (Celonis)"
        US1_CELONIS = "us1-celonis", "US1 (Celonis)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="make_connection",
    )
    api_token = EncryptedTextField()
    region = models.CharField(max_length=20, choices=Region.choices)
    organization_id = models.PositiveBigIntegerField(null=True, blank=True)
    team_id = models.PositiveBigIntegerField(null=True, blank=True)
    allowed_scenario_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "settings_make_connection"

    def __str__(self):
        return f"Make.com for {self.workspace.name}"
