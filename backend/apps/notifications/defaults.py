"""Platform default templates (P05-T02), English.

Rules (FR-M14-04, docs/07 EC-NOT): no scores, rankings, evaluations or reasons from screening in
any message; outcomes are respectful; every email points to the portal for details. In-app texts
are one short sentence. Organisations may override any template (P05-T10).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefaultTemplate:
    subject: str
    body_md: str
    inapp: str


DEFAULTS: dict[str, DefaultTemplate] = {
    "application_received": DefaultTemplate(
        "We received your application for {{ job_title }}",
        """Hello {{ recipient_name }},

Thank you for applying for **{{ job_title }}** at {{ organisation_name }}. Your application has
been received.

Your reference number is **{{ reference }}**. Please keep it for your records.

A person at {{ organisation_name }} makes every decision about your application. You can follow
its progress, or withdraw it, at any time:

[View your application]({{ application_url }})""",
        "Application received for {{ job_title }} (ref {{ reference }}).",
    ),
    "document_rejected_reupload": DefaultTemplate(
        "Please upload your document again",
        """Hello {{ recipient_name }},

We could not accept the file **{{ document_name }}**. {{ reason }}

Your application has not been lost. Please upload a new copy so the employer can see it:

[Upload a new file]({{ application_url }})""",
        "Please upload {{ document_name }} again.",
    ),
    "clarification_requested": DefaultTemplate(
        "{{ organisation_name }} has a question about your application",
        """Hello {{ recipient_name }},

{{ organisation_name }} would like a little more information about your application for
**{{ job_title }}**. Please reply by **{{ due_date }}**.

[Answer the question]({{ clarification_url }})

For your privacy the question itself is only shown in your account.""",
        "{{ organisation_name }} asked a question about your application for {{ job_title }}.",
    ),
    "clarification_reminder": DefaultTemplate(
        "Reminder: a question about your application is waiting",
        """Hello {{ recipient_name }},

This is a reminder that {{ organisation_name }} asked for more information about your
application for **{{ job_title }}**. The reply is due by **{{ due_date }}**.

[Answer the question]({{ clarification_url }})""",
        "Reminder: please answer the question about {{ job_title }} by {{ due_date }}.",
    ),
    "application_withdrawn_confirmation": DefaultTemplate(
        "Your application for {{ job_title }} has been withdrawn",
        """Hello {{ recipient_name }},

As you asked, your application **{{ reference }}** for **{{ job_title }}** at
{{ organisation_name }} has been withdrawn. The employer will no longer consider it.

If the vacancy is still open you can apply again from your account.""",
        "Your application for {{ job_title }} was withdrawn.",
    ),
    "draft_deadline_reminder": DefaultTemplate(
        "Your application for {{ job_title }} is not finished yet",
        """Hello {{ recipient_name }},

You started an application for **{{ job_title }}** at {{ organisation_name }}, but it has not
been submitted. Applications close on **{{ deadline }}**.

[Continue your application]({{ apply_url }})""",
        "Finish your application for {{ job_title }} before {{ deadline }}.",
    ),
    "draft_abandoned": DefaultTemplate(
        "The vacancy {{ job_title }} has closed",
        """Hello {{ recipient_name }},

The vacancy **{{ job_title }}** at {{ organisation_name }} closed before your application was
submitted, so it was not sent to the employer.

You can browse other open vacancies in your account.""",
        "{{ job_title }} closed before your application was submitted.",
    ),
    "shortlisted": DefaultTemplate(
        "Good news about your application for {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} would like to take your application for **{{ job_title }}** to the
next stage. They will contact you about the next steps.

[View your application]({{ application_url }})""",
        "{{ organisation_name }} moved your application for {{ job_title }} to the next stage.",
    ),
    "not_selected": DefaultTemplate(
        "Update on your application for {{ job_title }}",
        """Hello {{ recipient_name }},

Thank you for your interest in **{{ job_title }}** at {{ organisation_name }} and for the time
you took to apply.

After careful consideration, {{ organisation_name }} will not be taking your application further
for this vacancy. This decision was made by a person, and it is not a judgement of your worth or
potential.

We encourage you to apply for other roles that match your experience. We wish you every success.""",
        "There is an update on your application for {{ job_title }}.",
    ),
    "recruitment_paused": DefaultTemplate(
        "Recruitment for {{ job_title }} is paused",
        """Hello {{ recipient_name }},

{{ organisation_name }} has paused recruitment for **{{ job_title }}**. Your application or draft
is kept, and we will let you know when there is news.""",
        "Recruitment for {{ job_title }} is paused; your application is kept.",
    ),
    "invitation_staff": DefaultTemplate(
        "{{ inviter_name }} invited you to join {{ organisation_name }}",
        """Hello,

{{ inviter_name }} invited you to join **{{ organisation_name }}** on {{ platform_name }} as
**{{ role_name }}**.

[Accept the invitation]({{ invitation_url }})

If you were not expecting this invitation you can ignore this email.""",
        "You were invited to join {{ organisation_name }}.",
    ),
    "rights_request_update": DefaultTemplate(
        "Update on your data request {{ request_reference }}",
        """Hello {{ recipient_name }},

There is an update on your data request **{{ request_reference }}** with {{ organisation_name }}.
Its status is now: **{{ request_status }}**.

Please sign in to your account to see the details.""",
        "Your data request {{ request_reference }} is now: {{ request_status }}.",
    ),
    "recruiter_digest": DefaultTemplate(
        "{{ new_applications }} new applications for {{ job_title }}",
        """Hello {{ recipient_name }},

Here is your update for **{{ job_title }}** at {{ organisation_name }}:

- New applications: **{{ new_applications }}**
- Finished processing: **{{ processing_done }}**

AI-assisted suggestions require human review before any decision.

[Open the dashboard]({{ dashboard_url }})""",
        "{{ new_applications }} new applications for {{ job_title }}.",
    ),
    "note_mention": DefaultTemplate(
        "{{ mention_author }} mentioned you in a note",
        """Hello {{ recipient_name }},

{{ mention_author }} mentioned you in a note on an application for **{{ job_title }}**.

[Open the note]({{ note_url }})""",
        "{{ mention_author }} mentioned you on {{ job_title }}.",
    ),
    "clarification_answered": DefaultTemplate(
        "{{ candidate_name }} answered your question ({{ job_title }})",
        """Hello {{ recipient_name }},

{{ candidate_name }} has answered the clarification request on application
**{{ reference }}** for **{{ job_title }}**.

[Open the application]({{ application_url }})""",
        "{{ candidate_name }} answered your question on {{ job_title }}.",
    ),
    "clarification_expired": DefaultTemplate(
        "No answer yet from {{ candidate_name }} ({{ job_title }})",
        """Hello {{ recipient_name }},

The clarification request on application **{{ reference }}** for **{{ job_title }}** passed its
due date without an answer. Please decide how to proceed; the candidate can still send you a
message.

[Open the application]({{ application_url }})""",
        "The clarification for {{ candidate_name }} on {{ job_title }} is overdue.",
    ),
    "new_message": DefaultTemplate(
        "New message about {{ job_title }}",
        """Hello {{ recipient_name }},

You have a new message from {{ sender_name }} about **{{ job_title }}**. For your privacy the
message is only shown in your account.

[Read the message]({{ message_url }})""",
        "New message from {{ sender_name }} about {{ job_title }}.",
    ),
}
