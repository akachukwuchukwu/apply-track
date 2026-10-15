from rest_framework.routers import DefaultRouter

from .views import ApplicationViewSet, CompanyViewSet, ContactViewSet, InterviewViewSet

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("applications", ApplicationViewSet, basename="application")
router.register("contacts", ContactViewSet, basename="contact")
router.register("interviews", InterviewViewSet, basename="interview")

urlpatterns = router.urls
