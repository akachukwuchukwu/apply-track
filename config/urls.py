from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from rest_framework_simplejwt.views import TokenRefreshView

from tracker.views import DashboardStatsView, ThrottledTokenObtainPairView

urlpatterns = [
    path('', TemplateView.as_view(template_name='tracker/demo.html'), name='demo'),
    path('admin/', admin.site.urls),
    path('api/', include('tracker.urls')),
    path('api/dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
