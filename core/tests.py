from django.test import TestCase
from rest_framework.test import APIClient
from .models import User, Category, Ad, ProviderService


class AccessRulesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='client', password='pass12345', role='client')
        self.provider = User.objects.create_user(username='provider', password='pass12345', role='provider')
        self.admin = User.objects.create_user(username='admin', password='pass12345', role='admin', is_staff=True)
        self.category = Category.objects.create(name='Test', slug='test')

    def test_register_cannot_choose_admin_or_premium(self):
        response = self.client.post('/api/register/', {
            'username': 'new', 'password': 'pass12345', 'role': 'admin', 'subscription': 'premium'
        }, format='json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='new')
        self.assertEqual(user.role, 'client')
        self.assertEqual(user.subscription, 'freemium')

    def test_client_can_create_ad_for_self(self):
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/ads/', {
            'title': 'Need a business plan', 'description': 'Help', 'price': '1000', 'category': self.category.id
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['author'], self.user.id)

    def test_client_cannot_create_provider_service(self):
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/provider-services/', {
            'title': 'Service', 'description': 'Help', 'price': '1000', 'category': self.category.id
        }, format='json')
        self.assertEqual(response.status_code, 403)
