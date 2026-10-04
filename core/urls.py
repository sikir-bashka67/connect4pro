from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, CategoryViewSet, AdViewSet, ProviderServiceViewSet,
    FinancingViewSet, EventViewSet, DatabaseResourceViewSet,
    GrantProbabilityCalculatorView, PlatformAnalyticsView, ApplicationViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'ads', AdViewSet, basename='ad')
router.register(r'provider-services', ProviderServiceViewSet, basename='provider-service')
router.register(r'financing', FinancingViewSet, basename='financing')
router.register(r'events', EventViewSet, basename='event')
router.register(r'database-resources', DatabaseResourceViewSet, basename='database-resource')
router.register(r'applications', ApplicationViewSet, basename='application')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
    path('calculator/', GrantProbabilityCalculatorView.as_view(), name='grant-calculator'),
    path('analytics/', PlatformAnalyticsView.as_view(), name='platform-analytics'),
]
