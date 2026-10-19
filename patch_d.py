import pathlib, sys

VIEW_CLASS = '''class ProviderAnalyticsView(APIView):
    """Базовая аналитика кабинета провайдера. Только Premium."""
    permission_classes = [IsAuthenticated, IsPremium]

    def get(self, request):
        user = request.user
        if user.role not in ('provider', 'admin'):
            raise PermissionDenied('Аналитика доступна только провайдерам.')
        now = timezone.now()
        periods = {'day': now - timedelta(days=1), 'week': now - timedelta(days=7), 'month': now - timedelta(days=30)}
        profile = ProviderProfile.objects.filter(provider=user).first()

        def events(kind):
            if not profile:
                return AnalyticsEvent.objects.none()
            return AnalyticsEvent.objects.filter(event_type=kind, object_type='provider', object_id=profile.id)

        def by_period(qs):
            data = {k: qs.filter(created_at__gte=since).count() for k, since in periods.items()}
            data['all_time'] = qs.count()
            return data

        apps = Application.objects.filter(provider_service__provider=user)
        deals = Deal.objects.filter(provider=user)
        per_service = list(
            ProviderService.objects.filter(provider=user)
            .annotate(applications_count=Count('applications', distinct=True), deals_count=Count('deals', distinct=True))
            .values('id', 'title', 'applications_count', 'deals_count')
            .order_by('-applications_count', 'title'))
        return Response({
            'has_profile': bool(profile),
            'profile_views': by_period(events('click')),
            'profile_shares': by_period(events('share')),
            'applications_total': apps.count(),
            'applications_by_status': {s: apps.filter(status=s).count() for s, _ in Application.STATUS_CHOICES},
            'deals_by_status': {s: deals.filter(status=s).count() for s, _ in Deal.STATUS_CHOICES},
            'deals_completed_amount': str(deals.filter(status='completed').aggregate(s=Sum('amount'))['s'] or 0),
            'services': per_service,
        })


'''

RETRIEVE = '''    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        obj = self.get_object()
        if obj.provider_id != (request.user.id if request.user.is_authenticated else None):
            AnalyticsEvent.objects.create(
                event_type='click', user=request.user if request.user.is_authenticated else None,
                object_type='provider', object_id=obj.id)
        return response
'''

def rd(p):
    return pathlib.Path(p).read_text(encoding='utf-8')

def wr(p, s):
    pathlib.Path(p).write_text(s, encoding='utf-8', newline='\n')

def rep(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit('НЕ УДАЛОСЬ: %s (найдено совпадений: %d). Файл не изменён.' % (what, n))
    return s.replace(old, new)

v = rd('core/views.py')
u = rd('core/urls.py')
if 'ProviderAnalyticsView' in v or 'ProviderAnalyticsView' in u:
    sys.exit('Похоже, правки уже внесены (ProviderAnalyticsView найден). Ничего не делаю.')

v = rep(v, 'from django.db.models import Q, Count, Case, When, Value, IntegerField\n',
        'from django.db.models import Q, Count, Case, When, Value, IntegerField, Sum\n', 'импорт Sum')
v = rep(v, 'IsOwnerOrAdmin, IsProviderOwnerOrAdmin\n',
        'IsOwnerOrAdmin, IsProviderOwnerOrAdmin, IsPremium\n', 'импорт IsPremium')
anchor = "    def get_queryset(self):\n        return ProviderProfile.objects.all().select_related('provider')\n"
v = rep(v, anchor, anchor + RETRIEVE, 'метод retrieve у ProviderProfileViewSet')
v = rep(v, 'class TrackAnalyticsView(APIView):', VIEW_CLASS + 'class TrackAnalyticsView(APIView):', 'класс ProviderAnalyticsView')

u = rep(u, 'PayboxWebhookView,\n)', 'PayboxWebhookView, ProviderAnalyticsView,\n)', 'импорт во urls.py')
u = rep(u, "name='analytics-track'),",
        "name='analytics-track'),\n    path('analytics/provider/', ProviderAnalyticsView.as_view(), name='provider-analytics'),",
        'путь analytics/provider/')

wr('core/views.py', v)
wr('core/urls.py', u)
print('Готово: core/views.py и core/urls.py обновлены.')
