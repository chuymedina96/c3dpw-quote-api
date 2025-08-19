# quote/urls.py
from django.urls import re_path, path
from .views import QuoteAPIView, BatchQuoteAPIView, health

urlpatterns = [
    re_path(r"^api/quote/?$", QuoteAPIView.as_view(), name="quote-api"),
    re_path(r"^api/quote/batch/?$", BatchQuoteAPIView.as_view(), name="quote-batch"),
    path("api/health", health, name="health"),
]
