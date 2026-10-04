from django.db.models import Q
from rest_framework import viewsets, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from .permissions import IsPremiumOrReadOnly, IsAdminOrReadOnly, IsOwnerOrAdmin, IsProviderOwnerOrAdmin
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import User, Category, Ad, ProviderService, Financing, Event, DatabaseResource, Application
from .serializers import (
    RegisterSerializer, CategorySerializer, AdSerializer, ProviderServiceSerializer,
    FinancingSerializer, EventSerializer, DatabaseResourceSerializer, ApplicationSerializer,
)
from rest_framework.views import APIView


class AdViewSet(viewsets.ModelViewSet):
    queryset = Ad.objects.all()
    serializer_class = AdSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'author', 'is_completed']
    search_fields = ['title', 'description']
    ordering_fields = ['price', 'created_at']

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ('client', 'admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Объявления клиентов могут размещать только клиенты.')
        serializer.save(author=user)


class GrantProbabilityCalculatorView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        turnover = request.data.get('annual_turnover', 'up_to_100k')
        try:
            employees = int(request.data.get('employees_count', 1))
        except (TypeError, ValueError):
            employees = 1
        sector = request.data.get('sector', 'general')
        score = 50
        if employees > 5:
            score += 20
        if turnover in ['up_to_5m', 'up_to_10m', 'over_10m']:
            score += 25
        elif turnover in ['up_to_1m', 'up_to_500k']:
            score += 10
        probability = min(score, 95)
        return Response({
            'sector': sector,
            'calculated_probability_percent': probability,
            'recommendation': (
                'У вас высокие шансы на получение гранта в категории ' + sector
                if probability > 70 else
                'Рекомендуем доработать бизнес-план с помощью наших провайдеров.'
            )
        })


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class ProviderServiceViewSet(viewsets.ModelViewSet):
    queryset = ProviderService.objects.all()
    serializer_class = ProviderServiceSerializer
    permission_classes = [IsProviderOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'provider']
    search_fields = ['title', 'description']
    ordering_fields = ['price', 'created_at']

    def perform_create(self, serializer):
        if self.request.user.role not in ('provider', 'admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Размещать услуги могут только провайдеры.')
        serializer.save(provider=self.request.user)


class FinancingViewSet(viewsets.ModelViewSet):
    queryset = Financing.objects.all()
    serializer_class = FinancingSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['financing_type', 'sector']
    search_fields = ['title', 'description']
    ordering_fields = ['deadline', 'created_at']


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_type', 'sector', 'format']
    search_fields = ['title', 'description']
    ordering_fields = ['date_and_time']


class DatabaseResourceViewSet(viewsets.ModelViewSet):
    queryset = DatabaseResource.objects.all()
    serializer_class = DatabaseResourceSerializer
    permission_classes = [IsPremiumOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['resource_type', 'sector', 'is_premium_only']
    search_fields = ['title', 'sector']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and (user.subscription == 'premium' or user.role == 'admin'):
            return qs
        return qs.filter(is_premium_only=False)


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'provider_service', 'financing']
    ordering_fields = ['created_at']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Application.objects.none()
        if user.role == 'admin':
            return Application.objects.all()
        if user.role == 'provider':
            return Application.objects.filter(provider_service__provider=user)
        return Application.objects.filter(client=user)

    def perform_create(self, serializer):
        if self.request.user.role != 'client':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Заявки создают клиенты.')
        serializer.save(client=self.request.user)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()
        if user.role == 'admin':
            serializer.save()
        elif user.role == 'provider' and instance.provider_service and instance.provider_service.provider == user:
            serializer.save()
        else:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Недостаточно прав для изменения заявки.')


class PlatformAnalyticsView(APIView):
    def get(self, request):
        if not request.user.is_authenticated or request.user.role != 'admin':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Аналитика доступна только администратору.')
        return Response({
            'total_users': User.objects.count(),
            'total_providers': User.objects.filter(role='provider').count(),
            'total_clients': User.objects.filter(role='client').count(),
            'total_ads': Ad.objects.count(),
            'completed_ads': Ad.objects.filter(is_completed=True).count(),
            'total_services': ProviderService.objects.count(),
            'total_events': Event.objects.count(),
            'total_financing_programs': Financing.objects.count(),
            'total_applications': Application.objects.count(),
        })
