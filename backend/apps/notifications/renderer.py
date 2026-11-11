"""Safe template rendering (P05-T01).

Templates are Markdown with ``{{ variable }}`` placeholders - nothing else. There are no tags,
filters, attribute access or code, so an organisation's template cannot reach anything but the
values we pass. Variables are strict: an unknown placeholder fails validation when the template
is saved, and a missing value fails rendering (the caller then falls back to the platform default,
EC-NOT-05). Values are HTML-escaped before Markdown conversion and the HTML is sanitised with nh3.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

import markdown as md
import nh3

PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
ANY_BRACES = re.compile(r"\{\{|\}\}|\{%|%\}")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

ALLOWED_TAGS = {"p", "br", "strong", "em", "a", "ul", "ol", "li", "h2", "h3", "blockquote", "hr"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
MAX_SUBJECT = 200
MAX_BODY = 20_000


class TemplateValidationError(ValueError):
    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"{k}: {', '.join(v)}" for k, v in errors.items()))


class TemplateRenderError(ValueError):
    """A value needed by the template is missing (render fails safe)."""


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


def placeholders(text: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(text)))


def validate(subject: str, body_md: str, allowed: frozenset[str] | set[str]) -> list[str]:
    """Return the placeholders used, or raise :class:`TemplateValidationError`."""
    errors: dict[str, list[str]] = {}
    for field_name, text, limit in (
        ("subject", subject, MAX_SUBJECT),
        ("body_md", body_md, MAX_BODY),
    ):
        problems: list[str] = []
        if len(text) > limit:
            problems.append(f"Keep this under {limit} characters.")
        unknown = sorted(set(PLACEHOLDER.findall(text)) - set(allowed))
        if unknown:
            problems.append("Unknown variables: " + ", ".join(unknown) + ".")
        if ANY_BRACES.search(PLACEHOLDER.sub("", text)):
            problems.append("Only {{ variable }} placeholders are allowed.")
        if problems:
            errors[field_name] = problems
    if "\n" in subject or "\r" in subject:
        errors.setdefault("subject", []).append("The subject must be a single line.")
    if not body_md.strip():
        errors.setdefault("body_md", []).append("The message cannot be empty.")
    if errors:
        raise TemplateValidationError(errors)
    return placeholders(subject + "\n" + body_md)


def _substitute(text: str, context: dict[str, Any], *, escape: bool) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in context or context[name] is None:
            raise TemplateRenderError(f"Missing value for {name}")
        value = str(context[name])
        return html.escape(value, quote=True) if escape else value

    return PLACEHOLDER.sub(repl, text)


def _plain(markdown_text: str) -> str:
    text = LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", markdown_text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


def _html_body(markdown_text: str) -> str:
    raw = md.markdown(markdown_text, extensions=["sane_lists"], output_format="html")
    return nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"https", "http", "mailto"},
        link_rel="noopener noreferrer",
    )


LAYOUT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title></head>
<body style="margin:0;background:#f4f6fa;font-family:Arial,Helvetica,sans-serif;color:#1e293b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:8px" cellpadding="0" cellspacing="0">
<tr><td style="background:#1f4e94;color:#ffffff;padding:16px 24px;font-weight:bold;border-radius:8px 8px 0 0">{brand}</td></tr>
<tr><td style="padding:24px;line-height:1.5;font-size:15px">{body}</td></tr>
<tr><td style="padding:16px 24px;color:#475569;font-size:12px;border-top:1px solid #e2e8f0">{footer}</td></tr>
</table></td></tr></table></body></html>
"""  # noqa: E501

FOOTER = (
    "This is an automated message. Replies to this address are not read - please use the "
    "messages in your account instead."
)


def _footer(context: dict[str, Any]) -> tuple[str, str]:
    """Plain and HTML footer. EC-NOT-06: replies are not read, so point to the portal messages."""
    portal = str(context.get("portal_url") or "")
    if not portal.startswith(("https://", "http://")):
        return FOOTER, html.escape(FOOTER)
    text = f"{FOOTER} Sign in to read and send messages: {portal}"
    href = html.escape(portal, quote=True)
    link = f'<a href="{href}" style="color:#1f4e94">{html.escape(portal)}</a>'
    return text, f"{html.escape(FOOTER)} Sign in to read and send messages: {link}"


def render(subject: str, body_md: str, context: dict[str, Any], *, brand: str) -> Rendered:
    subject_out = _substitute(subject, context, escape=False).replace("\n", " ").strip()
    footer_text, footer_html = _footer(context)
    text = _plain(_substitute(body_md, context, escape=False)) + "\n--\n" + footer_text + "\n"
    body_html = _html_body(_substitute(body_md, context, escape=True))
    page = LAYOUT.format(
        title=html.escape(subject_out),
        brand=html.escape(brand),
        body=body_html,
        footer=footer_html,
    )
    return Rendered(subject=subject_out, text=text, html=page)
