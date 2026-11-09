"""Server-side rich-text sanitisation (nh3 allow-list, docs/06 §1).

Allowed: p, br, strong, em, ul, ol, li, h2-h4, a[href] (http/https/mailto) with
``rel="noopener nofollow ugc"``. Everything else is stripped (tags) or dropped (script/style
content).
"""

from __future__ import annotations

import nh3

ALLOWED_TAGS = {"p", "br", "strong", "em", "ul", "ol", "li", "h2", "h3", "h4", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_html(value: str | None) -> str:
    if not value:
        return ""
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel="noopener nofollow ugc",
        strip_comments=True,
    ).strip()
