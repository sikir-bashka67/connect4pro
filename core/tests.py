from django.test import TestCase
from rest_framework.test import APIClient
from .models import User, Category, Ad, ProviderService, ProviderProfile, ForumTopic


class BaseCase(TestCase):
    def setUp(self):
        self.api = APIClient()
        mk = User.objects.create_user
        self.client_u = mk(username='client', password='pass12345', role='client', email='c@x.kg',
                           what_i_offer='Бухгалтерия', consent_public_offer=True,
                           business_sector='IT', phone='+996700000001', first_name='Али')
        self.client2 = mk(username='client2', password='pass12345', role='client', email='c2@x.kg')
        self.provider = mk(username='provider', password='pass12345', role='provider', email='p@x.kg')
        self.admin = mk(username='admin', password='pass12345', role='admin', is_staff=True)
        self.premium = mk(username='prem', password='pass12345', role='client', subscription='premium')
        self.category = Category.objects.create(name='Test', slug='test')
        self.profile = ProviderProfile.objects.create(
            provider=self.provider, company_name='Acme', activity='Консалтинг', manager_name='Иван Иванов',
            description='d', services_description='s', phone='+996555000000', email='acme@x.kg')
        self.service = ProviderService.objects.create(
            provider=self.provider, title='БП', description='d', price=1000, phone='+996555111111')


class AccessRulesTests(BaseCase):
    def test_register_cannot_choose_admin_or_premium(self):
        # роль admin при регистрации отклоняется
        r = self.api.post('/api/register/', {
            'username': 'new', 'password': 'pass12345x', 'email': 'new@x.kg', 'role': 'admin'},
            format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username='new').exists())

        # подписку premium нельзя выбрать сразу: поле игнорируется
        r = self.api.post('/api/register/', {
            'username': 'new2', 'password': 'pass12345x', 'email': 'new2@x.kg', 'role': 'provider',
            'subscription': 'premium'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        u = User.objects.get(username='new2')
        self.assertEqual((u.role, u.subscription), ('provider', 'freemium'))
    def test_register_requires_unique_email_and_consent_for_offer(self):
        base = {'username': 'n2', 'password': 'pass12345x', 'email': 'c@x.kg'}
        self.assertEqual(self.api.post('/api/register/', base, format='json').status_code, 400)
        base.update(email='n2@x.kg', what_i_offer='Знаю маркетинг')
        self.assertEqual(self.api.post('/api/register/', base, format='json').status_code, 400)
        base['consent_public_offer'] = True
        self.assertEqual(self.api.post('/api/register/', base, format='json').status_code, 201)

    def test_client_can_create_ad_for_self(self):
        self.api.force_authenticate(self.client_u)
        r = self.api.post('/api/ads/', {'title': 'Нужен БП', 'description': 'Help', 'price': '1000',
                                        'category': self.category.id}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['author'], self.client_u.id)

    def test_client_cannot_create_provider_service(self):
        self.api.force_authenticate(self.client_u)
        r = self.api.post('/api/provider-services/', {'title': 'S', 'description': 'H', 'price': '1'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_freemium_cannot_enable_auto_bump(self):
        self.api.force_authenticate(self.client_u)
        r = self.api.post('/api/ads/', {'title': 'T', 'description': 'D', 'price': '1', 'auto_bump': True}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertFalse(Ad.objects.get(id=r.data['id']).auto_bump)


class OwnershipTests(BaseCase):
    def test_other_user_cannot_delete_forum_topic(self):
        t = ForumTopic.objects.create(title='t', author=self.client_u)
        self.api.force_authenticate(self.client2)
        self.assertEqual(self.api.delete(f'/api/forum/topics/{t.id}/').status_code, 403)
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.delete(f'/api/forum/topics/{t.id}/').status_code, 204)

    def test_guest_can_read_forum_but_not_write(self):
        self.assertEqual(self.api.get('/api/forum/topics/').status_code, 200)
        self.assertIn(self.api.post('/api/forum/topics/', {'title': 'x'}, format='json').status_code, (401, 403))

    def test_other_provider_cannot_delete_profile(self):
        other = User.objects.create_user(username='p2', password='pass12345', role='provider')
        self.api.force_authenticate(other)
        self.assertEqual(self.api.delete(f'/api/provider-profiles/{self.profile.id}/').status_code, 403)


class VisibilityTests(BaseCase):
    def _profile(self):
        r = self.api.get(f'/api/provider-profiles/{self.profile.id}/')
        self.assertEqual(r.status_code, 200)
        return r.data

    def test_guest_and_freemium_do_not_see_provider_contacts(self):
        for who in (None, self.client_u, self.provider.__class__.objects.create_user(username='p3', password='x12345678', role='provider')):
            self.api.force_authenticate(who)
            d = self._profile()
            for f in ('phone', 'email', 'manager_name', 'address', 'website'):
                self.assertNotIn(f, d)
            self.assertEqual(d['company_name'], 'Acme')

    def test_premium_owner_and_admin_see_provider_contacts(self):
        for who in (self.premium, self.provider, self.admin):
            self.api.force_authenticate(who)
            d = self._profile()
            self.assertEqual(d['phone'], '+996555000000')
            self.assertEqual(d['manager_name'], 'Иван Иванов')

    def test_service_contacts_hidden_for_freemium(self):
        r = self.api.get(f'/api/provider-services/{self.service.id}/')
        self.assertNotIn('phone', r.data)
        self.api.force_authenticate(self.premium)
        self.assertEqual(self.api.get(f'/api/provider-services/{self.service.id}/').data['phone'], '+996555111111')

    def test_client_directory_levels(self):
        r = self.api.get('/api/clients/directory/')
        self.assertEqual(r.status_code, 200)
        row = r.data['results'][0]
        self.assertEqual(set(row), {'id', 'what_i_offer'})
        self.api.force_authenticate(self.client2)
        row = self.api.get('/api/clients/directory/').data['results'][0]
        self.assertEqual(set(row), {'id', 'what_i_offer', 'business_sector'})
        self.api.force_authenticate(self.premium)
        row = self.api.get('/api/clients/directory/').data['results'][0]
        self.assertEqual(row['phone'], '+996700000001')
        self.assertEqual(row['first_name'], 'Али')

    def test_directory_excludes_users_without_consent(self):
        self.client2.what_i_offer = 'Секрет'
        self.client2.save()
        names = [x['what_i_offer'] for x in self.api.get('/api/clients/directory/').data['results']]
        self.assertNotIn('Секрет', names)


class AnalyticsTests(BaseCase):
    def test_track_rejects_unknown_event(self):
        r = self.api.post('/api/analytics/track/', {'event_type': 'hack'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post('/api/analytics/track/', {'event_type': 'visit'}, format='json')
        self.assertEqual(r.status_code, 201)

    def test_analytics_admin_only(self):
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.get('/api/analytics/').status_code, 403)
        self.api.force_authenticate(self.admin)
        self.assertEqual(self.api.get('/api/analytics/').status_code, 200)
