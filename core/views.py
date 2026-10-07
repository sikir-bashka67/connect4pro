from django.db.models import Q, Count
from django.utils import timezone
from django.core.mail import send_mail
from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .permissions import IsPremiumOrReadOnly, IsAdminOrReadOnly, IsOwnerOrAdmin, IsProviderOwnerOrAdmin
from .models import *
from .serializers import *
from rest_framework.views import APIView


class AdViewSet(viewsets.ModelViewSet):
    queryset = Ad.objects.all().select_related('author', 'category').prefetch_related('photos')
    serializer_class = AdSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'author', 'is_completed', 'auto_bump']
    search_fields = ['title', 'description', 'what_i_offer_optional']
    ordering_fields = ['price', 'created_at', 'last_bumped_at']

    def perform_create(self, serializer):
        if self.request.user.role not in ('client', 'admin'):
            raise PermissionDenied('Объявления клиентов могут размещать только клиенты.')
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def share(self, request, pk=None):
        AnalyticsEvent.objects.create(event_type='share', user=request.user, object_type='ad', object_id=self.get_object().id)
        return Response({'detail': 'Событие поделиться зарегистрировано.'})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete(self, request, pk=None):
        ad = self.get_object()
        if ad.author != request.user and request.user.role != 'admin':
            raise PermissionDenied('Изменять можно только своё объявление.')
        ad.is_completed = True
        ad.keep_listing = bool(request.data.get('keep_listing', False))
        ad.completion_requested_at = timezone.now()
        ad.save(update_fields=['is_completed', 'keep_listing', 'completion_requested_at'])
        return Response(AdSerializer(ad, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bump(self, request, pk=None):
        ad = self.get_object()
        if ad.author != request.user and request.user.role != 'admin':
            raise PermissionDenied('Изменять можно только своё объявление.')
        if not request.user.is_premium_active() and request.user.role != 'admin':
            raise PermissionDenied('Автоподнятие объявления доступно Premium.')
        ad.last_bumped_at = timezone.now()
        ad.auto_bump = True
        ad.save(update_fields=['last_bumped_at', 'auto_bump'])
        return Response({'detail': 'Объявление поднято.', 'last_bumped_at': ad.last_bumped_at})


class AdPhotoViewSet(viewsets.ModelViewSet):
    queryset = AdPhoto.objects.all().select_related('ad__author')
    serializer_class = AdPhotoSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        ad = serializer.validated_data['ad']
        if ad.author != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Фото может загружать только владелец объявления.')
        serializer.save()
    def perform_destroy(self, instance):
        if instance.ad.author != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Удалять фото может только владелец объявления.')
        instance.delete()


class ProviderProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProviderProfileSerializer
    def get_serializer_class(self):
        if not self.request.user.is_authenticated:
            return PublicProviderProfileSerializer
        return ProviderProfileSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    def get_queryset(self):
        return ProviderProfile.objects.all().select_related('provider')
    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ('provider', 'admin'):
            raise PermissionDenied('Профиль могут создавать только провайдеры.')
        provider = user if user.role == 'provider' else serializer.validated_data.get('provider')
        if provider is None or provider.role != 'provider':
            raise ValidationError({'provider': 'Укажите пользователя с ролью provider.'})
        if ProviderProfile.objects.filter(provider=provider).exists():
            raise ValidationError('У провайдера уже есть профиль.')
        serializer.save(provider=provider)
    def perform_update(self, serializer):
        obj = self.get_object()
        if self.request.user.role != 'admin' and obj.provider != self.request.user:
            raise PermissionDenied('Можно менять только свой профиль.')
        serializer.save()


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class ProviderServiceViewSet(viewsets.ModelViewSet):
    queryset = ProviderService.objects.all().select_related('provider', 'category').prefetch_related('photos')
    serializer_class = ProviderServiceSerializer
    permission_classes = [IsProviderOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'provider']
    search_fields = ['title', 'description']
    ordering_fields = ['price', 'created_at']
    def perform_create(self, serializer):
        if self.request.user.role not in ('provider', 'admin'):
            raise PermissionDenied('Размещать услуги могут только провайдеры.')
        serializer.save(provider=self.request.user)


class ProviderServicePhotoViewSet(viewsets.ModelViewSet):
    queryset = ProviderServicePhoto.objects.all().select_related('service__provider')
    serializer_class = ProviderServicePhotoSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        service = serializer.validated_data['service']
        if service.provider != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Фото может загружать только владелец услуги.')
        serializer.save()
    def perform_destroy(self, instance):
        if instance.service.provider != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Удалять фото может только владелец услуги.')
        instance.delete()


class FinancingViewSet(viewsets.ModelViewSet):
    queryset = Financing.objects.all().select_related('category')
    serializer_class = FinancingSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['financing_type', 'sector']
    search_fields = ['title', 'description', 'sector']
    ordering_fields = ['deadline', 'created_at']


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all().select_related('category')
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_type', 'sector', 'format']
    search_fields = ['title', 'description', 'sector']
    ordering_fields = ['date_and_time']


class DatabaseResourceViewSet(viewsets.ModelViewSet):
    queryset = DatabaseResource.objects.all().select_related('category')
    serializer_class = DatabaseResourceSerializer
    permission_classes = [IsPremiumOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['resource_type', 'sector', 'is_premium_only']
    search_fields = ['title', 'sector']
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and user.is_premium_active():
            return qs
        return qs.filter(is_premium_only=False)


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'provider_service', 'financing']
    ordering_fields = ['created_at']
    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated: return Application.objects.none()
        if user.role == 'admin': return Application.objects.all()
        if user.role == 'provider': return Application.objects.filter(provider_service__provider=user)
        return Application.objects.filter(client=user)
    def perform_create(self, serializer):
        if self.request.user.role != 'client': raise PermissionDenied('Заявки создают клиенты.')
        serializer.save(client=self.request.user)
    def perform_update(self, serializer):
        instance = self.get_object(); user = self.request.user
        if user.role == 'admin' or (user.role == 'provider' and instance.provider_service and instance.provider_service.provider == user):
            serializer.save()
        else: raise PermissionDenied('Недостаточно прав.')


class ForumTopicViewSet(viewsets.ModelViewSet):
    queryset = ForumTopic.objects.all().select_related('author').prefetch_related('posts')
    serializer_class = ForumTopicSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['topic_type', 'is_closed']
    search_fields = ['title']
    ordering_fields = ['created_at', 'updated_at']
    def perform_create(self, serializer): serializer.save(author=self.request.user)
    def perform_update(self, serializer):
        if self.request.user != self.get_object().author and self.request.user.role != 'admin': raise PermissionDenied('Тему может менять только автор или админ.')
        serializer.save()


class ForumPostViewSet(viewsets.ModelViewSet):
    queryset = ForumPost.objects.all().select_related('author', 'topic')
    serializer_class = ForumPostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ['topic', 'author']
    def perform_create(self, serializer):
        topic = serializer.validated_data['topic']
        if topic.is_closed: raise ValidationError('Тема закрыта.')
        serializer.save(author=self.request.user)
    def perform_update(self, serializer):
        if self.request.user != self.get_object().author and self.request.user.role != 'admin': raise PermissionDenied('Менять сообщение может только автор или админ.')
        serializer.save()


class NotificationSubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self): return NotificationSubscription.objects.filter(user=self.request.user)
    def perform_create(self, serializer):
        if NotificationSubscription.objects.filter(user=self.request.user).exists(): raise ValidationError('Настройки уже существуют.')
        serializer.save(user=self.request.user, email=self.request.user.email)
    def perform_update(self, serializer): serializer.save(email=serializer.validated_data.get('email', self.request.user.email))


class PaymentTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return PaymentTransaction.objects.all() if self.request.user.role == 'admin' else PaymentTransaction.objects.filter(user=self.request.user)
    def perform_create(self, serializer): serializer.save(user=self.request.user)
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        payment = self.get_object()
        if request.user.role != 'admin': raise PermissionDenied('Подтверждать платежи может только администратор.')
        payment.status = 'paid'; payment.paid_at = timezone.now(); payment.save(update_fields=['status', 'paid_at'])
        if payment.description.lower().startswith('premium'):
            user = payment.user; user.subscription = 'premium'; user.premium_until = timezone.now() + timezone.timedelta(days=30); user.save(update_fields=['subscription','premium_until'])
        return Response(PaymentTransactionSerializer(payment).data)


class DealViewSet(viewsets.ModelViewSet):
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        u=self.request.user
        if u.role=='admin': return Deal.objects.all()
        return Deal.objects.filter(Q(client=u)|Q(provider=u)).distinct()
    def perform_create(self, serializer):
        data = serializer.validated_data
        service = data.get('provider_service')
        ad = data.get('ad')
        if service:
            provider=service.provider
            if provider == self.request.user: raise ValidationError('Нельзя создать сделку с собой.')
            serializer.save(client=self.request.user, provider=provider)
        else:
            if ad.author == self.request.user: raise ValidationError('Нельзя создать сделку с собой.')
            if self.request.user.role != 'provider': raise PermissionDenied('Для сделки по объявлению нужен провайдер.')
            serializer.save(client=ad.author, provider=self.request.user)
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        deal=self.get_object()
        deal.status='completed'; deal.completed_at=timezone.now(); deal.save(update_fields=['status','completed_at'])
        if deal.ad: deal.ad.is_completed=True; deal.ad.completion_requested_at=timezone.now(); deal.ad.save(update_fields=['is_completed','completion_requested_at'])
        return Response(DealSerializer(deal).data)


class GrantProbabilityCalculatorView(APIView):
    permission_classes=[AllowAny]
    def post(self, request):
        turnover=request.data.get('annual_turnover','up_to_100k')
        try: employees=int(request.data.get('employees_count',1))
        except (TypeError,ValueError): employees=1
        sector=request.data.get('sector','general'); score=50
        if employees>5: score+=20
        if turnover in ['up_to_5m','up_to_10m','over_10m']: score+=25
        elif turnover in ['up_to_1m','up_to_500k']: score+=10
        probability=min(score,95)
        return Response({'sector':sector,'calculated_probability_percent':probability,'recommendation':'Рекомендуем доработать бизнес-план с помощью наших провайдеров.' if probability<=70 else 'У вас высокий расчетный показатель.'})


class RegisterView(generics.CreateAPIView):
    queryset=User.objects.all(); serializer_class=RegisterSerializer; permission_classes=[AllowAny]


class MeView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request): return Response(UserSerializer(request.user).data)
    def patch(self, request):
        serializer=UserSerializer(request.user,data=request.data,partial=True); serializer.is_valid(raise_exception=True); serializer.save(); return Response(serializer.data)


class PremiumClientDirectoryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        if not request.user.is_premium_active(): raise PermissionDenied('Доступен только Premium.')
        qs=User.objects.filter(role__in=['client','provider']).values('first_name','last_name','company_name','email','phone','region','business_sector','employees_count','what_i_offer','what_i_seek')
        return Response(list(qs))


class ClientDirectoryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        qs=User.objects.filter(role='client')
        data=[]
        for u in qs:
            item={'first_name':u.first_name,'last_name':u.last_name,'business_sector':u.business_sector,'what_i_offer':u.what_i_offer}
            if request.user.is_premium_active():
                item.update({'email':u.email,'phone':u.phone,'region':u.region,'employees_count':u.employees_count,'company_name':u.company_name,'what_i_seek':u.what_i_seek})
            data.append(item)
        return Response(data)


class PlatformAnalyticsView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        if request.user.role!='admin': raise PermissionDenied('Аналитика доступна только администратору.')
        now=timezone.now(); day=now-timezone.timedelta(days=1); week=now-timezone.timedelta(days=7); month=now-timezone.timedelta(days=30); year=now-timezone.timedelta(days=365)
        def visits(since=None):
            q=AnalyticsEvent.objects.filter(event_type='visit')
            return q.filter(created_at__gte=since).count() if since else q.count()
        top=AnalyticsEvent.objects.filter(event_type='click',object_type='ad').values('object_id').annotate(c=Count('id')).order_by('-c').first()
        return Response({
            'visitors_day':visits(day),'visitors_week':visits(week),'visitors_month':visits(month),'visitors_year':visits(year),'visitors_all_time':visits(),
            'total_users':User.objects.count(),'total_providers':User.objects.filter(role='provider').count(),'total_clients':User.objects.filter(role='client').count(),
            'premium_subscribers':User.objects.filter(subscription='premium').count(),'total_ads':Ad.objects.count(),'provider_ads':ProviderService.objects.count(),
            'completed_deals':Deal.objects.filter(status='completed').count(),'transaction_volume':sum((x.amount for x in PaymentTransaction.objects.filter(status='paid')), 0),
            'forum_topics':ForumTopic.objects.count(),'forum_posts':ForumPost.objects.count(),'shares':AnalyticsEvent.objects.filter(event_type='share').count(),
            'traffic_sources':list(AnalyticsEvent.objects.filter(event_type='traffic').values('source').annotate(count=Count('id')).order_by('-count')),
            'most_clicked_ad':top,
            'users_by_region':list(User.objects.values('region').annotate(count=Count('id')).order_by('-count')),
            'users_by_turnover':list(User.objects.values('annual_turnover').annotate(count=Count('id')).order_by('-count')),
            'users_by_employees':list(User.objects.values('employees_count').annotate(count=Count('id')).order_by('-count')),
        })


class TrackAnalyticsView(APIView):
    permission_classes=[AllowAny]
    def post(self, request):
        AnalyticsEvent.objects.create(event_type=request.data.get('event_type','visit'), user=request.user if request.user.is_authenticated else None, object_type=request.data.get('object_type',''), object_id=request.data.get('object_id'), source=request.data.get('source',''))
        return Response({'tracked':True}, status=status.HTTP_201_CREATED)
