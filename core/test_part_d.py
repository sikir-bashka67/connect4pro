from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AnalyticsEvent, Application, Deal, ProviderProfile, ProviderService, User


class ProviderAnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        mk = User.objects.create_user
        self.prem = mk(username='pp', password='pass12345', role='provider', email='pp@x.kg', subscription='premium')
        self.free = mk(username='pf', password='pass12345', role='provider', email='pf@x.kg')
        self.client_u = mk(username='cc', password='pass12345', role='client', email='cc@x.kg')
        self.profile = ProviderProfile.objects.create(
            provider=self.prem, company_name='A', activity='IT', manager_name='M',
            description='d', services_description='s')
        self.svc = ProviderService.objects.create(provider=self.prem, title='Site', description='d', price=100)

    def test_free_provider_gets_403(self):
        self.api.force_authenticate(self.free)
        self.assertEqual(self.api.get('/api/analytics/provider/').status_code, 403)

    def test_client_gets_403(self):
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.get('/api/analytics/provider/').status_code, 403)

    def test_premium_sees_own_numbers(self):
        Application.objects.create(client=self.client_u, provider_service=self.svc)
        Deal.objects.create(provider_service=self.svc, client=self.client_u, provider=self.prem,
                            status='completed', amount=500)
        AnalyticsEvent.objects.create(event_type='click', object_type='provider', object_id=self.profile.id)
        AnalyticsEvent.objects.create(event_type='share', object_type='provider', object_id=self.profile.id)
        self.api.force_authenticate(self.prem)
        r = self.api.get('/api/analytics/provider/')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['profile_views']['all_time'], 1)
        self.assertEqual(d['profile_shares']['all_time'], 1)
        self.assertEqual(d['applications_total'], 1)
        self.assertEqual(d['applications_by_status']['pending'], 1)
        self.assertEqual(d['deals_by_status']['completed'], 1)
        self.assertEqual(float(d['deals_completed_amount']), 500.0)
        self.assertEqual(d['services'][0]['applications_count'], 1)

    def test_profile_view_counted_for_others_not_owner(self):
        url = f'/api/provider-profiles/{self.profile.id}/'
        self.api.force_authenticate(self.prem)
        self.api.get(url)
        self.assertEqual(AnalyticsEvent.objects.filter(object_type='provider').count(), 0)
        self.api.force_authenticate(self.client_u)
        self.api.get(url)
        self.assertEqual(AnalyticsEvent.objects.filter(event_type='click', object_type='provider').count(), 1)
