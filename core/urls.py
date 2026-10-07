from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, ProviderProfileViewSet, CategoryViewSet, AdViewSet, AdPhotoViewSet, ProviderServiceViewSet,
    ProviderServicePhotoViewSet, FinancingViewSet, EventViewSet, DatabaseResourceViewSet,
    GrantProbabilityCalculatorView, PlatformAnalyticsView, TrackAnalyticsView, ApplicationViewSet,
    ForumTopicViewSet, ForumPostViewSet, NotificationSubscriptionViewSet, PaymentTransactionViewSet,
    DealViewSet, MeView, PremiumClientDirectoryView, ClientDirectoryView,
)

router = DefaultRouter()
for prefix, view, basename in [
    ('provider-profiles', ProviderProfileViewSet, 'provider-profile'),
    ('categories', CategoryViewSet, 'category'), ('ads', AdViewSet, 'ad'), ('ad-photos', AdPhotoViewSet, 'ad-photo'),
    ('provider-services', ProviderServiceViewSet, 'provider-service'), ('service-photos', ProviderServicePhotoViewSet, 'service-photo'),
    ('financing', FinancingViewSet, 'financing'), ('events', EventViewSet, 'event'),
    ('database-resources', DatabaseResourceViewSet, 'database-resource'), ('applications', ApplicationViewSet, 'application'),
    ('forum/topics', ForumTopicViewSet, 'forum-topic'), ('forum/posts', ForumPostViewSet, 'forum-post'),
    ('notifications', NotificationSubscriptionViewSet, 'notification'), ('payments', PaymentTransactionViewSet, 'payment'),
    ('deals', DealViewSet, 'deal'),
]: router.register(prefix, view, basename=basename)

urlpatterns = [
    path('', include(router.urls)), path('register/', RegisterView.as_view(), name='register'),
    path('me/', MeView.as_view(), name='me'), path('clients/directory/', ClientDirectoryView.as_view(), name='clients-directory'), path('premium/clients/', PremiumClientDirectoryView.as_view(), name='premium-clients'),
    path('calculator/', GrantProbabilityCalculatorView.as_view(), name='grant-calculator'),
    path('analytics/', PlatformAnalyticsView.as_view(), name='platform-analytics'), path('analytics/track/', TrackAnalyticsView.as_view(), name='analytics-track'),
]
