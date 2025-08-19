# quote_backend/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("quote.urls")),   # pulls in /api/quote and /api/health
]
