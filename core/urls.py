from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdViewSet, RegisterView

router = DefaultRouter()
router.register(r'ads', AdViewSet, basename='ad')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', RegisterView.as_view(), name='register'),
]