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
    "organisation_closed": DefaultTemplate(
        "Update on your application for {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} has closed its account on {{ platform_name }}, so your application
**{{ reference }}** for **{{ job_title }}** will not progress here. This is not a decision about
you or your application.

Your data is kept only as long as the employer's retention policy requires and is then
anonymised. You can download or delete your data at any time from your account.""",
        "{{ organisation_name }} closed its account; your application for {{ job_title }} "
        "will not progress.",
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
    "rights_request_confirm": DefaultTemplate(
        "Please confirm your data request {{ request_reference }}",
        """Hello {{ recipient_name }},

We received a request from your account: **{{ request_type }}** (reference
**{{ request_reference }}**).

To protect your data we act only after you confirm it was you:
[Confirm my request]({{ confirm_url }})

If you did not make this request, ignore this email and consider changing your password.""",
        "Please confirm your data request {{ request_reference }} from the link in your email.",
    ),
    "rights_request_received": DefaultTemplate(
        "Data request {{ request_reference }} needs handling",
        """Hello {{ recipient_name }},

A candidate confirmed a data request with {{ organisation_name }}: **{{ request_type }}**
(reference **{{ request_reference }}**). It is due by **{{ due_date }}**.

[Open privacy requests]({{ privacy_url }})""",
        "New data request {{ request_reference }} is due by {{ due_date }}.",
    ),
    "rights_request_due": DefaultTemplate(
        "Data request {{ request_reference }} is due by {{ due_date }}",
        """Hello {{ recipient_name }},

Data request **{{ request_reference }}** with {{ organisation_name }} is due by **{{ due_date }}**
and is not completed yet.

[Open privacy requests]({{ privacy_url }})""",
        "Data request {{ request_reference }} is due by {{ due_date }}.",
    ),
    "retention_report": DefaultTemplate(
        "Retention preview for {{ organisation_name }}",
        """Hello {{ recipient_name }},

Under your retention policy, **{{ due_count }}** applications to vacancies that closed long ago
will be anonymised in the coming days. {{ held_count }} are kept because of a legal hold.

To keep something longer, place a legal hold before then.

[Open privacy settings]({{ privacy_url }})""",
        "{{ due_count }} old applications will be anonymised under your retention policy.",
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
    "interview_invitation": DefaultTemplate(
        "Interview invitation: {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} invites you to a **{{ interview_stage }}** for **{{ job_title }}**.

- When: {{ interview_when }}
- How: {{ interview_mode }}
- Where: {{ interview_where }}

If you were offered several times, choose the one that suits you in your account. You can also
add the interview to your calendar or ask for another time there.

[See the interview details]({{ interview_url }})""",
        "{{ organisation_name }} invited you to an interview for {{ job_title }}.",
    ),
    "interview_booked": DefaultTemplate(
        "Interview booked: {{ job_title }} ({{ reference }})",
        """Hello {{ recipient_name }},

The candidate for application **{{ reference }}** ({{ job_title }}) booked the
**{{ interview_stage }}** for {{ interview_when }}.

[Open the interview]({{ interview_url }})""",
        "Interview booked for {{ reference }}: {{ interview_when }}.",
    ),
    "interview_reminder": DefaultTemplate(
        "Reminder: your interview for {{ job_title }}",
        """Hello {{ recipient_name }},

This is a reminder of your **{{ interview_stage }}** with {{ organisation_name }} for
**{{ job_title }}**.

- When: {{ interview_when }}
- How: {{ interview_mode }}
- Where: {{ interview_where }}

[See the interview details]({{ interview_url }})""",
        "Reminder: interview for {{ job_title }}, {{ interview_when }}.",
    ),
    "interview_rescheduled": DefaultTemplate(
        "New time for your interview: {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} moved your **{{ interview_stage }}** for **{{ job_title }}**.

- New time: {{ interview_when }}
- How: {{ interview_mode }}
- Where: {{ interview_where }}

Note from the employer: {{ reason }}

Please update your calendar from your account.

[See the interview details]({{ interview_url }})""",
        "Your interview for {{ job_title }} moved to {{ interview_when }}.",
    ),
    "interview_cancelled": DefaultTemplate(
        "Interview cancelled: {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} cancelled the **{{ interview_stage }}** for **{{ job_title }}** planned for
{{ interview_when }}.

Note from the employer: {{ reason }}

Your application is still open unless you hear otherwise; any update will appear in your account.

[View your application]({{ application_url }})""",
        "The interview for {{ job_title }} on {{ interview_when }} was cancelled.",
    ),
    "offer_issued": DefaultTemplate(
        "An offer from {{ organisation_name }}: {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} has made you an offer for **{{ job_title }}**. The offer letter and its
terms are in your account, where you can accept or decline it.

Please reply by **{{ deadline }}**.

[See the offer]({{ offer_url }})""",
        "{{ organisation_name }} made you an offer for {{ job_title }}.",
    ),
    "offer_expiring": DefaultTemplate(
        "Your offer for {{ job_title }} expires soon",
        """Hello {{ recipient_name }},

This is a reminder that the offer from {{ organisation_name }} for **{{ job_title }}** is open
until **{{ deadline }}**. You can accept or decline it in your account.

[See the offer]({{ offer_url }})""",
        "Your offer for {{ job_title }} is open until {{ deadline }}.",
    ),
    "offer_withdrawn": DefaultTemplate(
        "Update on your offer for {{ job_title }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} has withdrawn the offer for **{{ job_title }}**.

Note from the employer: {{ reason }}

[View your application]({{ application_url }})""",
        "{{ organisation_name }} withdrew the offer for {{ job_title }}.",
    ),
    "offer_accepted": DefaultTemplate(
        "Offer accepted: {{ job_title }} ({{ reference }})",
        """Hello {{ recipient_name }},

The candidate for application **{{ reference }}** accepted the offer for **{{ job_title }}**.
{{ openings_note }}

Record the hire once the start is confirmed.

[Open the offer]({{ offer_url }})""",
        "Offer accepted for {{ reference }} ({{ job_title }}).",
    ),
    "offer_declined": DefaultTemplate(
        "Offer declined: {{ job_title }} ({{ reference }})",
        """Hello {{ recipient_name }},

The candidate for application **{{ reference }}** declined the offer for **{{ job_title }}**.

[Open the offer]({{ offer_url }})""",
        "Offer declined for {{ reference }} ({{ job_title }}).",
    ),
    "offer_expired": DefaultTemplate(
        "Offer expired: {{ job_title }} ({{ reference }})",
        """Hello {{ recipient_name }},

The offer for application **{{ reference }}** ({{ job_title }}) expired without an answer. You can
contact the candidate through the application's messages, or issue a new offer.

[Open the offer]({{ offer_url }})""",
        "The offer for {{ reference }} ({{ job_title }}) expired.",
    ),
    "talent_pool_reconfirm": DefaultTemplate(
        "Stay in {{ organisation_name }}'s talent pool?",
        """Hello {{ recipient_name }},

You asked {{ organisation_name }} to keep your details for future vacancies. That ends on
{{ expires_on }}.

If you would like to stay, confirm it in your account. If you do nothing, your details simply stop
being available to them; you can also leave or delete them at any time.

[Manage your talent pool choices]({{ privacy_url }})""",
        "Your place in {{ organisation_name }}'s talent pool ends on {{ expires_on }}.",
    ),
    "talent_pool_invitation": DefaultTemplate(
        "{{ organisation_name }} invites you to apply: {{ job_title }}",
        """Hello {{ recipient_name }},

You are in {{ organisation_name }}'s talent pool, and they think this vacancy could suit you:
**{{ job_title }}**.

Applying is entirely up to you, and you apply in the usual way.

[View the vacancy]({{ job_url }})

You can leave the talent pool at any time: [manage your choices]({{ privacy_url }})""",
        "{{ organisation_name }} invites you to apply for {{ job_title }}.",
    ),
    "ai_override_alert": DefaultTemplate(
        "Rubric review suggested: {{ job_title }}",
        """Hello {{ recipient_name }},

Over the last 30 days, {{ override_rate }} of {{ decisions }} shortlist decisions for
**{{ job_title }}** went against the AI band. That usually means the rubric does not match what
your team is looking for.

Consider reviewing the vacancy's criteria and weights. Nothing changes automatically: people keep
making every decision.

[Open the reports]({{ report_url }})""",
        "{{ override_rate }} of decisions for {{ job_title }} went against the AI band.",
    ),
    "hired_welcome": DefaultTemplate(
        "Welcome to {{ organisation_name }}",
        """Hello {{ recipient_name }},

{{ organisation_name }} has confirmed your appointment as **{{ job_title }}**, starting on
{{ start_date }}. Congratulations!

The employer will contact you about your first day. Your application stays in your account.

[View your application]({{ application_url }})""",
        "Welcome to {{ organisation_name }}: you start as {{ job_title }} on {{ start_date }}.",
    ),
}
