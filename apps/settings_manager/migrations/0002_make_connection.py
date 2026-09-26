import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.common.encryption


class Migration(migrations.Migration):
    dependencies = [
        ("settings_manager", "0001_initial"),
        ("workspaces", "0003_alter_workspace_primary_color_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MakeConnection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("api_token", apps.common.encryption.EncryptedTextField()),
                (
                    "region",
                    models.CharField(
                        choices=[
                            ("eu1", "EU1"),
                            ("eu2", "EU2"),
                            ("us1", "US1"),
                            ("us2", "US2"),
                            ("eu1-celonis", "EU1 (Celonis)"),
                            ("us1-celonis", "US1 (Celonis)"),
                        ],
                        max_length=20,
                    ),
                ),
                ("organization_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("team_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("allowed_scenario_ids", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "workspace",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="make_connection",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={"db_table": "settings_make_connection"},
        ),
    ]
