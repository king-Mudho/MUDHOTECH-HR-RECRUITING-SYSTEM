"""Staff single sign-on with Google / Microsoft (P15-T03, allauth socialaccount).

Rules:

* SSO signs in **existing staff** only - nobody gets an account by signing in with Google or
  Microsoft (``is_open_for_signup`` is False); new staff still join by invitation.
* The identity provider must vouch for the email address, and the person must be an active member
  of an organisation whose policy enables SSO for that email's domain (``sso_enabled`` +
  ``sso_domains``). Otherwise the login is refused.
* SSO does not replace the MHRS MFA policy: privileged roles still need an MHRS authenticator,
  and allauth asks for it after the provider login like after a password login.
"""

from __future__ import annotations

from typing import Any

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import JsonResponse


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


def sso_allowed(user: Any, email: str) -> bool:
    from apps.organisations.models import Membership, OrganisationPolicy

    domain = email_domain(email)
    if not domain:
        return False
    org_ids = (
        Membership.objects.unscoped()
        .filter(user=user, status=Membership.Status.ACTIVE)
        .values_list("organisation_id", flat=True)
    )
    for policy in OrganisationPolicy.objects.filter(
        organisation_id__in=list(org_ids), sso_enabled=True
    ):
        if domain in {d.strip().lower() for d in (policy.sso_domains or [])}:
            return True
    return False


def _refuse(message: str) -> ImmediateHttpResponse:
    return ImmediateHttpResponse(
        JsonResponse({"error": {"code": "sso_not_allowed", "message": message}}, status=403)
    )


class SocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request: Any, sociallogin: Any) -> bool:
        return False

    def pre_social_login(self, request: Any, sociallogin: Any) -> None:
        from apps.accounts.models import User

        verified = [e.email for e in sociallogin.email_addresses if getattr(e, "verified", False)]
        if not verified:
            raise _refuse("Your organisation account must have a verified email address.")
        email = verified[0].strip().lower()
        user = sociallogin.user if sociallogin.is_existing else None
        if user is None:
            user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is None or not sso_allowed(user, email):
            raise _refuse(
                "Single sign-on is not enabled for this account. Sign in with your email and "
                "password, or ask your organisation admin."
            )
        if not sociallogin.is_existing:
            sociallogin.connect(request, user)
