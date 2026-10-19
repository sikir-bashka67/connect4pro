"""Демо-данные: seed_demo."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Ad, DatabaseResource, Event, Financing, ProviderService, User


def seed(**kw):
    out = StringIO()
    call_command('seed_demo', stdout=out, force=True, **kw)
    return out.getvalue()


def counts():
    return tuple(m.objects.count() for m in (User, Ad, ProviderService, Financing, Event, DatabaseResource))


class SeedDemoTests(TestCase):
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())

    def test_idempotent(self):
        seed()
        first = counts()
        self.assertTrue(all(first))
        seed()
        self.assertEqual(counts(), first)

    def test_demo_accounts_and_provider_analytics(self):
        seed()
        api = APIClient()
        r = api.post('/api/token/', {'username': 'demo_premium_client', 'password': 'demo12345'}, format='json')
        self.assertEqual(r.status_code, 200)
        api.force_authenticate(User.objects.get(username='demo_provider_premium'))
        r = api.get('/api/analytics/provider/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()['profile_views']['all_time'], 1)
        api.force_authenticate(User.objects.get(username='demo_provider'))
        self.assertEqual(api.get('/api/analytics/provider/').status_code, 403)

    def test_clear(self):
        seed()
        seed(clear=True)
        self.assertFalse(User.objects.filter(username__startswith='demo_').exists())
        self.assertFalse(Financing.objects.filter(title='Грант для IT-стартапов').exists())
