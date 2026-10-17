import hmac
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q, Count, Case, When, Value, IntegerField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail
from rest_framework import viewsets, mixins, generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.throttling import AnonRateThrottle
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError, NotAuthenticated, NotFound, Throttled
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .permissions import IsPremiumOrReadOnly, IsAdminOrReadOnly, IsOwnerOrAdmin, IsProviderOwnerOrAdmin
from .models import *
from .serializers import *
from rest_framework.views import APIView
from . import payments, services
from .exceptions import PaymentRequired


class TagFilterMixin:
    """?tag=it — точное совпадение с одним из тегов (теги хранятся как 'a,b,c')."""

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        tag = (self.request.query_params.get('tag') or '').strip().lstrip('#').strip().lower()
        if tag:
            qs = qs.filter(Q(tags=tag) | Q(tags__startswith=tag + ',') | Q(tags__contains=',' + tag + ',')
                           | Q(tags__endswith=',' + tag))
        return qs


class AdViewSet(TagFilterMixin, viewsets.ModelViewSet):
    serializer_class = AdSerializer
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'author', 'is_completed', 'auto_bump', 'listing_type']
    search_fields = ['title', 'description', 'what_i_offer_optional', 'tags']
    ordering_fields = ['price', 'created_at', 'last_bumped_at', 'sort_at']
    # по умолчанию: сначала объявления Premium о купле-продаже доли, затем по свежести/поднятию
    ordering = ['-priority', '-sort_at', '-id']

    def get_queryset(self):
        now = timezone.now()
        premium_author = Q(author__role='admin') | (
            Q(author__subscription='premium')
            & (Q(author__premium_until__isnull=True) | Q(author__premium_until__gt=now)))
        return (Ad.objects.all().select_related('author', 'category').prefetch_related('photos')
                .annotate(
                    sort_at=Coalesce('last_bumped_at', 'created_at'),
                    priority=Case(
                        When(premium_author & Q(listing_type__in=Ad.SHARE_TYPES), then=Value(1)),
                        default=Value(0), output_field=IntegerField())))

    def perform_create(self, serializer):
        if self.request.user.role not in ('client', 'admin'):
            raise PermissionDenied('Объявления клиентов могут размещать только клиенты.')
        serializer.save(author=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        AnalyticsEvent.objects.create(
            event_type='click', user=request.user if request.user.is_authenticated else None,
            object_type='ad', object_id=int(kwargs['pk']))
        return response

    @action(detail=True, methods=['post'], permission_classes=[AllowAny], throttle_classes=[AnonRateThrottle])
    def share(self, request, pk=None):
        AnalyticsEvent.objects.create(
            event_type='share', user=request.user if request.user.is_authenticated else None,
            object_type='ad', object_id=self.get_object().id, source=str(request.data.get('source', ''))[:100])
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
    def keep(self, request, pk=None):
        """«Оставить объявление»: подтвердить актуальность (сбрасывает напоминание) или вернуть завершённое."""
        ad = self.get_object()
        if ad.author != request.user and request.user.role != 'admin':
            raise PermissionDenied('Изменять можно только своё объявление.')
        ad.is_completed = False
        ad.keep_listing = True
        ad.completion_requested_at = None
        ad.last_reminder_at = timezone.now()
        ad.save(update_fields=['is_completed', 'keep_listing', 'completion_requested_at', 'last_reminder_at'])
        return Response(AdSerializer(ad, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bump(self, request, pk=None):
        """Ручное поднятие объявления (Premium)."""
        ad = self.get_object()
        if ad.author != request.user and request.user.role != 'admin':
            raise PermissionDenied('Изменять можно только своё объявление.')
        if not request.user.is_premium_active():
            raise PermissionDenied('Поднятие объявления доступно Premium.')
        ad.last_bumped_at = timezone.now()
        ad.save(update_fields=['last_bumped_at'])
        return Response({'detail': 'Объявление поднято.', 'last_bumped_at': ad.last_bumped_at})

    @action(detail=True, methods=['post'], url_path='auto-bump', permission_classes=[IsAuthenticated])
    def auto_bump_toggle(self, request, pk=None):
        """Включить/выключить автоподнятие по расписанию (Premium). Тело: {"enabled": true|false}."""
        ad = self.get_object()
        if ad.author != request.user and request.user.role != 'admin':
            raise PermissionDenied('Изменять можно только своё объявление.')
        raw = request.data.get('enabled', True)
        enabled = raw if isinstance(raw, bool) else str(raw).strip().lower() in ('1', 'true', 'yes', 'on')
        if enabled and not request.user.is_premium_active():
            raise PermissionDenied('Автоподнятие объявления доступно Premium.')
        ad.auto_bump = enabled
        ad.save(update_fields=['auto_bump'])
        return Response({'auto_bump': ad.auto_bump})


class AdPhotoViewSet(viewsets.ModelViewSet):
    queryset = AdPhoto.objects.all().select_related('ad__author')
    serializer_class = AdPhotoSerializer
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        ad = serializer.validated_data['ad']
        if ad.author != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Фото может загружать только владелец объявления.')
        if ad.photos.count() >= 5:
            raise ValidationError('Не больше 5 фото в объявлении.')
        serializer.save()
    def perform_update(self, serializer):
        if serializer.instance.ad.author != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Менять фото может только владелец объявления.')
        serializer.save()
    def perform_destroy(self, instance):
        if instance.ad.author != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Удалять фото может только владелец объявления.')
        instance.delete()


class ProviderProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProviderProfileSerializer
    permission_classes = [IsProviderOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['activity', 'provider']
    search_fields = ['company_name', 'activity', 'description', 'services_description']
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


class ProviderServiceViewSet(TagFilterMixin, viewsets.ModelViewSet):
    queryset = ProviderService.objects.all().select_related('provider', 'category').prefetch_related('photos')
    serializer_class = ProviderServiceSerializer
    permission_classes = [IsProviderOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'provider']
    search_fields = ['title', 'description', 'tags']
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
        if service.photos.count() >= 5:
            raise ValidationError('Не больше 5 фото в услуге.')
        serializer.save()
    def perform_update(self, serializer):
        if serializer.instance.service.provider != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Менять фото может только владелец услуги.')
        serializer.save()
    def perform_destroy(self, instance):
        if instance.service.provider != self.request.user and self.request.user.role != 'admin':
            raise PermissionDenied('Удалять фото может только владелец услуги.')
        instance.delete()


class FinancingViewSet(TagFilterMixin, viewsets.ModelViewSet):
    queryset = Financing.objects.all().select_related('category')
    serializer_class = FinancingSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['financing_type', 'sector']
    search_fields = ['title', 'description', 'sector', 'tags']
    ordering_fields = ['deadline', 'created_at']


class EventViewSet(TagFilterMixin, viewsets.ModelViewSet):
    queryset = Event.objects.all().select_related('category')
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_type', 'sector', 'format']
    search_fields = ['title', 'description', 'sector', 'tags']
    ordering_fields = ['date_and_time']


class DatabaseResourceViewSet(viewsets.ModelViewSet):
    queryset = DatabaseResource.objects.all().select_related('category')
    serializer_class = DatabaseResourceSerializer
    permission_classes = [IsPremiumOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['resource_type', 'sector', 'is_premium_only']
    search_fields = ['title', 'sector']
    ordering = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.filter(is_premium_only=False)
        if user.is_premium_active():  # включает админа
            return qs
        # подписка закончилась: свободные материалы + то, что куплено в пакете
        return qs.filter(Q(is_premium_only=False) | Q(unlocks__user=user, unlocks__source='pack')).distinct()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['unlocks'] = services.unlock_map(self.request.user)
        return ctx

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def quota(self, request):
        """Сколько проектов и бизнес-планов уже открыто и сколько осталось."""
        return Response({t: services.quota_status(request.user, t) for t in services.QUOTA_TYPES})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def unlock(self, request, pk=None):
        """Открыть проект / бизнес-план. Повторное открытие не тратит лимит."""
        resource = self.get_object()
        if request.user.role != 'admin' and resource.resource_type in services.QUOTA_TYPES:
            services.unlock_resource(request.user, resource)
        ctx = self.get_serializer_context()
        return Response(DatabaseResourceSerializer(resource, context=ctx).data)


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return ApplicationReviewSerializer
        return ApplicationSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'provider_service', 'financing']
    ordering_fields = ['created_at']
    def get_queryset(self):
        user = self.request.user
        base = Application.objects.select_related('client', 'provider_service', 'financing')
        if not user.is_authenticated: return Application.objects.none()
        if user.role == 'admin': return base
        if user.role == 'provider': return base.filter(provider_service__provider=user)
        return base.filter(client=user)
    def perform_create(self, serializer):
        if self.request.user.role != 'client': raise PermissionDenied('Заявки создают клиенты.')
        serializer.save(client=self.request.user)
    def perform_update(self, serializer):
        instance = self.get_object(); user = self.request.user
        if user.role == 'admin' or (user.role == 'provider' and instance.provider_service and instance.provider_service.provider == user):
            serializer.save()
        else: raise PermissionDenied('Недостаточно прав.')
    def perform_destroy(self, instance):
        if self.request.user.role != 'admin' and instance.client != self.request.user:
            raise PermissionDenied('Удалять заявку может только её автор или админ.')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='create-deal')
    def create_deal(self, request, pk=None):
        """CRM: провайдер превращает заявку на свою услугу в сделку (сумма по умолчанию — цена услуги)."""
        app = self.get_object()
        svc = app.provider_service
        if svc is None:
            raise ValidationError('Сделку можно создать только по заявке на услугу.')
        if request.user.role != 'admin' and svc.provider != request.user:
            raise PermissionDenied('Недостаточно прав.')
        if app.status == 'rejected':
            raise ValidationError('Заявка отклонена: сначала одобрите её.')
        try:
            amount = Decimal(str(request.data.get('amount', svc.price)))
        except (InvalidOperation, ValueError):
            raise ValidationError({'amount': 'Некорректная сумма.'})
        if amount < 0:
            raise ValidationError({'amount': 'Сумма не может быть отрицательной.'})
        deal = Deal.objects.filter(provider_service=svc, client=app.client, status='started').first()
        created = deal is None
        if created:
            deal = Deal.objects.create(provider_service=svc, client=app.client, provider=svc.provider, amount=amount)
        if app.status == 'pending':
            app.status = 'approved'
            app.save(update_fields=['status'])
        return Response(DealSerializer(deal, context={'request': request}).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ForumTopicViewSet(viewsets.ModelViewSet):
    queryset = ForumTopic.objects.all().select_related('author').prefetch_related('posts')
    serializer_class = ForumTopicSerializer
    permission_classes = [IsOwnerOrAdmin]
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
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['topic', 'author']
    ordering_fields = ['created_at']
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


class PaymentTransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Платежи только читаются. Создаются через checkout, подтверждаются шлюзом (webhook) или админом."""
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return PaymentTransaction.objects.all() if user.role == 'admin' else PaymentTransaction.objects.filter(user=user)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def prices(self, request):
        return Response({k: {'amount': str(v), 'currency': 'KGS'} for k, v in settings.PRICES_KGS.items()})

    @action(detail=False, methods=['post'], permission_classes=[AllowAny], throttle_classes=[AnonRateThrottle])
    def checkout(self, request):
        """Создать платёж. Тело: {"purpose": "premium|calculator|pack_project|pack_business_plan"}."""
        purpose = request.data.get('purpose')
        if not isinstance(purpose, str) or purpose not in settings.PRICES_KGS:
            raise ValidationError({'purpose': f'Допустимо: {", ".join(settings.PRICES_KGS)}.'})
        user = request.user if request.user.is_authenticated else None
        if purpose != 'calculator':
            if user is None:
                raise NotAuthenticated('Войдите, чтобы оплатить.')
        if purpose in ('pack_project', 'pack_business_plan') and not user.is_premium_active():
            raise PermissionDenied('Пакеты баз данных доступны подписчикам Premium.')
        if purpose == 'calculator' and user is not None and user.is_premium_active():
            raise ValidationError('Для Premium калькулятор бесплатный.')
        tx = payments.create_transaction(user, purpose)
        try:
            invoice = payments.get_gateway().create_invoice(tx, request)
        except payments.PaymentGatewayError as exc:
            tx.status = 'failed'
            tx.save(update_fields=['status'])
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        tx.external_id = invoice.get('external_id', '')
        tx.payment_url = invoice.get('payment_url', '')
        tx.save(update_fields=['external_id', 'payment_url'])
        data = PaymentTransactionSerializer(tx).data
        # токен выдаётся один раз: по нему гость потом предъявляет оплату калькулятора
        data['access_token'] = tx.access_token
        data['gateway'] = settings.PAYMENT_GATEWAY
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='stub-pay', permission_classes=[AllowAny],
            throttle_classes=[AnonRateThrottle])
    def stub_pay(self, request, pk=None):
        """ТЕСТОВАЯ оплата без шлюза. Выключена, когда PAYMENT_GATEWAY != stub или отключена в настройках."""
        if not (settings.PAYMENT_GATEWAY == 'stub' and settings.PAYMENTS_STUB_ENABLED):
            raise NotFound()
        tx = get_object_or_404(PaymentTransaction, pk=pk)
        token = str(request.data.get('access_token', ''))
        if not tx.access_token or not hmac.compare_digest(token.encode('utf-8'), tx.access_token.encode('utf-8')):
            raise PermissionDenied('Неверный токен платежа.')
        tx = payments.mark_paid(tx, external_id=f'stub-{tx.id}')
        return Response(PaymentTransactionSerializer(tx).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Ручное подтверждение админом (например, оплата переводом)."""
        if request.user.role != 'admin':
            raise PermissionDenied('Подтверждать платежи может только администратор.')
        tx = payments.mark_paid(self.get_object())
        return Response(PaymentTransactionSerializer(tx).data)


class PayboxWebhookView(APIView):
    """result_url для Paybox: шлюз сообщает итог оплаты. Подпись проверяется, сумма сверяется."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _handle(self, request):
        if settings.PAYMENT_GATEWAY != 'paybox':
            raise NotFound()
        gw = payments.PayboxGateway()
        script = request.path.rstrip('/').rsplit('/', 1)[-1]
        data = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        params = {**request.query_params.dict(), **{k: str(v) for k, v in data.items()}}
        try:
            if not gw.verify_callback(script, params):
                return Response({'detail': 'Неверная подпись.'}, status=status.HTTP_403_FORBIDDEN)
        except payments.PaymentGatewayError:
            return Response({'detail': 'Шлюз не настроен.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        def reply(st, text=''):
            return HttpResponse(gw.callback_response(script, st, text), content_type='application/xml')

        try:
            tx = PaymentTransaction.objects.get(pk=int(params.get('pg_order_id', '')))
            amount = Decimal(params.get('pg_amount', ''))
        except (PaymentTransaction.DoesNotExist, ValueError, InvalidOperation):
            return reply('rejected', 'Платёж не найден')
        if amount != tx.amount:
            return reply('rejected', 'Неверная сумма')
        if str(params.get('pg_result')) == '1':
            payments.mark_paid(tx, external_id=str(params.get('pg_payment_id', '')))
        elif tx.status == 'pending':
            tx.status = 'failed'
            tx.save(update_fields=['status'])
        return reply('ok')

    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)


class DealViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Сделки. Менять и удалять напрямую нельзя: только действия complete / cancel / amount."""
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        u = self.request.user
        qs = Deal.objects.select_related('ad', 'provider_service', 'client', 'provider')
        if u.role == 'admin':
            return qs
        return qs.filter(Q(client=u) | Q(provider=u))

    def perform_create(self, serializer):
        data = serializer.validated_data
        service, ad, user = data.get('provider_service'), data.get('ad'), self.request.user
        if service:
            if user.role != 'client':
                raise PermissionDenied('Сделку по услуге открывает клиент.')
            if Deal.objects.filter(client=user, provider_service=service, status='started').exists():
                raise ValidationError('Сделка по этой услуге уже открыта.')
            serializer.save(client=user, provider=service.provider)
        else:
            if user.role != 'provider':
                raise PermissionDenied('Для сделки по объявлению нужен провайдер.')
            if Deal.objects.filter(ad=ad, provider=user, status='started').exists():
                raise ValidationError('Сделка по этому объявлению уже открыта.')
            serializer.save(client=ad.author, provider=user)

    @staticmethod
    def _open(deal):
        if deal.status != 'started':
            raise ValidationError('Сделка уже завершена или отменена.')

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        deal = self.get_object()
        self._open(deal)
        deal.status = 'completed'
        deal.completed_at = timezone.now()
        deal.save(update_fields=['status', 'completed_at'])
        if deal.ad:
            deal.ad.is_completed = True
            deal.ad.completion_requested_at = timezone.now()
            deal.ad.save(update_fields=['is_completed', 'completion_requested_at'])
        return Response(DealSerializer(deal, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        deal = self.get_object()
        self._open(deal)
        deal.status = 'cancelled'
        deal.save(update_fields=['status'])
        return Response(DealSerializer(deal, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='amount')
    def set_amount(self, request, pk=None):
        deal = self.get_object()
        if request.user.role != 'admin' and deal.provider != request.user:
            raise PermissionDenied('Сумму сделки указывает провайдер.')
        self._open(deal)
        try:
            amount = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, ValueError):
            raise ValidationError({'amount': 'Некорректная сумма.'})
        if amount < 0:
            raise ValidationError({'amount': 'Сумма не может быть отрицательной.'})
        deal.amount = amount
        deal.save(update_fields=['amount'])
        return Response(DealSerializer(deal, context={'request': request}).data)


class GrantProbabilityCalculatorView(APIView):
    """Калькулятор вероятности: бесплатно для Premium, остальным — по разовой оплате.
    Оплата предъявляется полями payment_id + access_token (из /payments/checkout/)."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        turnover = request.data.get('annual_turnover', 'up_to_100k')
        if turnover not in dict(User.TURNOVER_CHOICES):
            raise ValidationError({'annual_turnover': 'Недопустимое значение оборота.'})
        try:
            employees = int(request.data.get('employees_count', 1))
            if employees < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError({'employees_count': 'Должно быть неотрицательным целым числом.'})
        sector = str(request.data.get('sector', 'general'))[:150]
        financing = None
        fid = request.data.get('financing')
        if fid not in (None, ''):
            try:
                financing = Financing.objects.get(pk=int(fid))
            except (TypeError, ValueError, Financing.DoesNotExist):
                raise ValidationError({'financing': 'Программа финансирования не найдена.'})

        user = request.user
        if not (user.is_authenticated and user.is_premium_active()):
            # входные данные проверены выше, чтобы оплата не сгорала из-за ошибки в форме
            payments.consume_calculator_payment(request.data.get('payment_id'), request.data.get('access_token'))

        score = 50
        if employees > 5:
            score += 20
        if turnover in ['up_to_5m', 'up_to_10m', 'over_10m']:
            score += 25
        elif turnover in ['up_to_1m', 'up_to_500k']:
            score += 10
        recommendation = None
        if financing is not None:
            # расчёт под конкретную программу: совпадение сектора, тип программы, срок подачи заявок
            program_sector = (financing.sector or '').strip().lower()
            own_sector = sector.strip().lower()
            if program_sector and own_sector and own_sector != 'general':
                score += 10 if (program_sector in own_sector or own_sector in program_sector) else -10
            if financing.financing_type == 'investment' and turnover in ['up_to_5m', 'up_to_10m', 'over_10m']:
                score += 5
            score = max(5, score)
        probability = min(score, 95)
        if financing is not None and financing.deadline and financing.deadline < timezone.localdate():
            probability = min(probability, 5)
            recommendation = 'Срок подачи заявок по этой программе истёк.'
        if recommendation is None:
            recommendation = ('Рекомендуем доработать бизнес-план с помощью наших провайдеров.' if probability <= 70
                              else 'У вас высокий расчетный показатель.')
        result = {'sector': sector, 'calculated_probability_percent': probability, 'recommendation': recommendation}
        if financing is not None:
            result['financing'] = {'id': financing.id, 'title': financing.title}
        return Response(result)


class RegisterView(generics.CreateAPIView):
    queryset=User.objects.all(); serializer_class=RegisterSerializer; permission_classes=[AllowAny]


class MeView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request): return Response(UserSerializer(request.user).data)
    def patch(self, request):
        serializer=UserSerializer(request.user,data=request.data,partial=True); serializer.is_valid(raise_exception=True); serializer.save(); return Response(serializer.data)


class ClientDirectoryView(generics.ListAPIView):
    """База данных МСБ. Что видно — решает ClientDirectorySerializer по статусу зрителя (ТЗ)."""
    permission_classes = [AllowAny]
    serializer_class = ClientDirectorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['business_sector', 'region']
    search_fields = ['what_i_offer', 'business_sector']

    def get_queryset(self):
        # в базе только клиенты, давшие согласие на публикацию. Не-Premium видят тех, кто заполнил
        # «я предлагаю»; Premium — ещё и тех, кто отметил «я ищу» (ТЗ: «если отмечает, появляется в БД МСБ»)
        has_offer = Q(what_i_offer__isnull=False) & ~Q(what_i_offer='')
        has_seek = Q(what_i_seek__isnull=False) & ~Q(what_i_seek='')
        visible = (has_offer | has_seek) if viewer_is_premium(self.request) else has_offer
        return (User.objects.filter(role='client', consent_public_offer=True, is_active=True)
                .filter(visible).order_by('-date_joined'))


# старый адрес оставлен для совместимости
PremiumClientDirectoryView = ClientDirectoryView


class PriceHintsView(APIView):
    """Рекомендуемые цены на услуги из ТЗ — подсказки в форме объявления."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(services.PRICE_HINTS)


class PlatformAnalyticsView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self, request):
        if request.user.role!='admin': raise PermissionDenied('Аналитика доступна только администратору.')
        now=timezone.now(); day=now-timedelta(days=1); week=now-timedelta(days=7); month=now-timedelta(days=30); year=now-timedelta(days=365)
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
            'most_clicked_ad_title': (Ad.objects.filter(pk=top['object_id']).values_list('title', flat=True).first() if top else None),
            'users_by_region':list(User.objects.values('region').annotate(count=Count('id')).order_by('-count')),
            'users_by_turnover':list(User.objects.values('annual_turnover').annotate(count=Count('id')).order_by('-count')),
            'users_by_employees':list(User.objects.values('employees_count').annotate(count=Count('id')).order_by('-count')),
        })


class TrackAnalyticsView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[AnonRateThrottle]
    def post(self, request):
        event_type=request.data.get('event_type','visit')
        if event_type not in dict(AnalyticsEvent.EVENT_CHOICES):
            raise ValidationError({'event_type': 'Недопустимый тип события.'})
        try:
            object_id=int(request.data['object_id']) if request.data.get('object_id') not in (None,'') else None
        except (TypeError, ValueError):
            raise ValidationError({'object_id': 'Должно быть числом.'})
        AnalyticsEvent.objects.create(event_type=event_type, user=request.user if request.user.is_authenticated else None, object_type=str(request.data.get('object_type',''))[:50], object_id=object_id, source=str(request.data.get('source',''))[:100])
        return Response({'tracked':True}, status=status.HTTP_201_CREATED)


class PublicUserView(generics.RetrieveAPIView):
    """Публичный профиль пользователя (для кнопки «Профиль» в объявлениях и на форуме)."""
    permission_classes = [AllowAny]
    serializer_class = PublicUserSerializer

    def get_queryset(self):
        qs = User.objects.filter(is_active=True)
        user = self.request.user
        if user.is_authenticated and user.role == 'admin':
            return qs
        return qs.exclude(role='admin')


MESSAGES_PER_HOUR = 30


class MessageViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Личные сообщения. Каждый видит только свою переписку."""
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        return Message.objects.filter(Q(sender=u) | Q(recipient=u)).select_related('sender', 'recipient')

    def perform_create(self, serializer):
        u = self.request.user
        since = timezone.now() - timedelta(hours=1)
        if Message.objects.filter(sender=u, created_at__gte=since).count() >= MESSAGES_PER_HOUR:
            raise Throttled(detail='Слишком много сообщений за час. Попробуйте позже.')
        serializer.save(sender=u)

    @action(detail=False, methods=['get'])
    def conversations(self, request):
        """Список собеседников: последнее сообщение и число непрочитанных."""
        u = request.user
        convs = {}
        for m in self.get_queryset().order_by('-created_at', '-id')[:1000]:
            other = m.recipient if m.sender_id == u.id else m.sender
            c = convs.get(other.id)
            if c is None:
                c = convs[other.id] = {
                    'user': {'id': other.id, 'name': display_name(other)},
                    'last_text': m.text[:120], 'last_at': m.created_at, 'unread': 0}
            if m.recipient_id == u.id and m.read_at is None:
                c['unread'] += 1
        return Response(list(convs.values()))

    @action(detail=False, methods=['get'], url_path=r'with/(?P<user_id>\d+)')
    def thread(self, request, user_id=None):
        """Переписка с одним человеком. Открытие помечает входящие прочитанными."""
        other = get_object_or_404(User, pk=user_id, is_active=True)
        qs = self.get_queryset().filter(Q(sender=other) | Q(recipient=other))
        qs.filter(recipient=request.user, sender=other, read_at__isnull=True).update(read_at=timezone.now())
        last = list(qs.order_by('-created_at', '-id')[:200])[::-1]
        return Response({
            'user': {'id': other.id, 'name': display_name(other)},
            'messages': MessageSerializer(last, many=True, context={'request': request}).data,
        })

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'unread': Message.objects.filter(recipient=request.user, read_at__isnull=True).count()})
