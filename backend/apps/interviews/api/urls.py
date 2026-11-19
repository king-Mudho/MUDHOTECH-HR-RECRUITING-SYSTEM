from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/interviews/", v.InterviewListView.as_view(), name="hr-interviews"),
    path(
        "hr/applications/<uuid:application_id>/interviews/",
        v.ApplicationInterviewsView.as_view(),
        name="hr-application-interviews",
    ),
    path("hr/interviews/<uuid:interview_id>/", v.InterviewView.as_view(), name="hr-interview"),
    path(
        "hr/interviews/<uuid:interview_id>/reschedule/",
        v.InterviewRescheduleView.as_view(),
        name="hr-interview-reschedule",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/cancel/",
        v.InterviewCancelView.as_view(),
        name="hr-interview-cancel",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/no-show/",
        v.InterviewNoShowView.as_view(),
        name="hr-interview-no-show",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/complete/",
        v.InterviewCompleteView.as_view(),
        name="hr-interview-complete",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/scorecards/",
        v.InterviewScorecardsView.as_view(),
        name="hr-interview-scorecards",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/scorecard/",
        v.MyScorecardView.as_view(),
        name="hr-interview-my-scorecard",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/scorecard/submit/",
        v.MyScorecardSubmitView.as_view(),
        name="hr-interview-my-scorecard-submit",
    ),
    path(
        "hr/interviews/<uuid:interview_id>/feedback/",
        v.InterviewFeedbackView.as_view(),
        name="hr-interview-feedback",
    ),
    path(
        "hr/jobs/<uuid:job_id>/scorecard-templates/",
        v.JobScorecardTemplatesView.as_view(),
        name="hr-job-scorecard-templates",
    ),
    # candidate
    path(
        "applications/<uuid:application_id>/interviews/",
        v.CandidateApplicationInterviewsView.as_view(),
        name="candidate-application-interviews",
    ),
    path(
        "interviews/<uuid:interview_id>/book/",
        v.CandidateBookView.as_view(),
        name="candidate-interview-book",
    ),
    path(
        "interviews/<uuid:interview_id>/calendar.ics",
        v.CandidateCalendarView.as_view(),
        name="candidate-interview-calendar",
    ),
]
