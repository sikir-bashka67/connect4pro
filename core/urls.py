from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdViewSet, RegisterView, OrderViewSet

router = DefaultRouter()
router.register(r'ads', AdViewSet, basename='ad')
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
]