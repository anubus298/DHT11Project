from django.urls import path
from . import views, api

urlpatterns = [
    path("test/", views.test),
    path("api/", api.dlist, name="json"),
    path("api/statistics", api.getStatistics, name="json"),
    path("api/avg/months", api.getMonthsAverage, name="json"),
    path("api/avg/days", api.getDailyAverage, name="json"),
    path("api/post", api.Dhtviews.as_view(), name="json"),
    
]
