from django.urls import path, re_path

from .public import (
    JobsFeedView,
    PublicJobDetailView,
    PublicJobListView,
    PublicJobQuestionsView,
    SitemapView,
)

urlpatterns = [
    path("jobs/", PublicJobListView.as_view(), name="jobs-public-list"),
    re_path(r"^jobs/feed\.(?P<fmt>rss|json)/?$", JobsFeedView.as_view(), name="jobs-feed"),
    path("sitemap.xml", SitemapView.as_view(), name="jobs-sitemap"),
    path("jobs/<str:slug>/", PublicJobDetailView.as_view(), name="jobs-public-detail"),
    path(
        "jobs/<str:slug>/questions/",
        PublicJobQuestionsView.as_view(),
        name="jobs-public-questions",
    ),
]
