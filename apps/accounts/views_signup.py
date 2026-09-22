from allauth.account.views import SignupView
from django.http import JsonResponse
from django.shortcuts import render

from apps.members.models import Invitation


class InvitePrefillSignupView(SignupView):
    """Signup view that pre-fills and locks the email when a pending
    invite token is in the session."""

    def closed(self, *args, **kwargs):
        """Render registration closed response with 403 status, supporting JSON API requests."""
        accept_header = self.request.headers.get("accept", "")
        content_type = self.request.content_type or ""
        if "application/json" in accept_header or "application/json" in content_type:
            return JsonResponse(
                {
                    "error": "registration_disabled",
                    "detail": "User registration is currently disabled.",
                },
                status=403,
            )
        return render(self.request, "account/signup_closed.html", status=403)

    def _invited_email(self):
        token = self.request.session.get("pending_invite_token")
        if not token:
            return None
        invitation = Invitation.objects.filter(
            token=token,
            accepted_at__isnull=True,
        ).first()
        if invitation and not invitation.is_expired:
            return invitation.email
        return None

    def get_initial(self):
        initial = super().get_initial()
        email = self._invited_email()
        if email:
            initial["email"] = email
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invited_email_locked"] = bool(self._invited_email())
        return ctx
