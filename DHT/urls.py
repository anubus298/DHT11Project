from django.urls import path
from . import views, api

urlpatterns = [
    path("api/post", api.dlist, name="api_json"),
    path("api/statistics", api.getStatistics, name="statistics_json"),
    path("api/avg/months", api.getMonthsAverage, name="avg_months_json"),
    path("api/avg/days", api.getDailyAverage, name="avg_days_json"),
]
