from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("", include("apps.api.conversations.urls")),
]
