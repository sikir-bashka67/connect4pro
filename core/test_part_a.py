"""Блок A: регистрация/профиль (согласие, «я ищу»), объявления (валюта, теги, «оставить объявление»), подсказки цен."""
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Ad, Category, User


class PartABase(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        mk = User.objects.create_user
        self.client_u = mk(username='cl', password='pass12345', role='client', email='cl@x.kg')
        self.premium = mk(username='pr', password='pass12345', role='client', email='pr@x.kg', subscription='premium')
        self.seeker = mk(username='seek', password='pass12345', role='client', email='s@x.kg',
                         what_i_seek='Ищу инвестора', consent_public_offer=True, first_name='Сидор')
        self.cat = Category.objects.create(name='Бизнес-планы', slug='bp')

    def post_ad(self, **extra):
        body = {'title': 'Нужен бизнес-план', 'description': 'Для кафе', 'price': '10000'}
        body.update(extra)
        self.api.force_authenticate(self.client_u)
        return self.api.post('/api/ads/', body, format='json')


class RegistrationProfileTests(PartABase):
    def test_register_seek_requires_consent(self):
        base = {'username': 'n1', 'password': 'pass12345x', 'email': 'n1@x.kg', 'what_i_seek': 'Партнёры'}
        self.assertEqual(self.api.post('/api/register/', base, format='json').status_code, 400)
        base['consent_public_offer'] = True
        self.assertEqual(self.api.post('/api/register/', base, format='json').status_code, 201)

    def test_register_accepts_blank_optional_fields_like_the_form_sends(self):
        r = self.api.post('/api/register/', {
            'username': 'n2', 'password': 'pass12345x', 'email': 'n2@x.kg', 'role': 'provider',
            'first_name': '', 'last_name': '', 'birth_year': None, 'company_name': 'Acme', 'phone': '',
            'website_or_social': '', 'region': '', 'business_sector': ''}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(User.objects.get(username='n2').role, 'provider')

    def test_patch_me_full_profile_and_consent_rule(self):
        self.api.force_authenticate(self.client_u)
        body = {'first_name': 'Али', 'employees_count': 7, 'annual_turnover': 'up_to_1m', 'region': 'Чуй',
                'what_i_offer': 'Маркетинг', 'what_i_seek': '', 'website_or_social': '', 'birth_year': None}
        r = self.api.patch('/api/me/', {**body, 'consent_public_offer': False}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch('/api/me/', {**body, 'consent_public_offer': True}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.client_u.refresh_from_db()
        self.assertEqual((self.client_u.employees_count, self.client_u.annual_turnover), (7, 'up_to_1m'))

    def test_seeker_visible_only_to_premium_in_directory(self):
        names = lambda: [x.get('first_name') for x in self.api.get('/api/clients/directory/').data['results']]
        self.assertNotIn('Сидор', names())                      # гость
        self.api.force_authenticate(self.client_u)
        self.assertNotIn('Сидор', names())                      # Free
        self.api.force_authenticate(self.premium)
        self.assertIn('Сидор', names())                         # Premium
        row = [x for x in self.api.get('/api/clients/directory/').data['results'] if x.get('first_name') == 'Сидор'][0]
        self.assertEqual(row['what_i_seek'], 'Ищу инвестора')


class AdFieldsTests(PartABase):
    def test_currency_defaults_to_kgs_and_accepts_usd(self):
        r = self.post_ad()
        self.assertEqual((r.status_code, r.data['currency']), (201, 'KGS'))
        r = self.post_ad(currency='USD')
        self.assertEqual((r.status_code, r.data['currency']), (201, 'USD'))
        self.assertEqual(self.post_ad(currency='EUR').status_code, 400)

    def test_tags_are_normalised_and_filterable(self):
        r = self.post_ad(tags=' IT, #Маркетинг ,it', category=self.cat.id)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['tags'], 'it,маркетинг')
        self.post_ad(title='Другое', tags='бухгалтерия')
        self.api.force_authenticate(None)
        titles = lambda q: [x['title'] for x in self.api.get('/api/ads/' + q).data['results']]
        self.assertEqual(titles('?tag=it'), ['Нужен бизнес-план'])
        self.assertEqual(titles('?tag=%23Маркетинг'), ['Нужен бизнес-план'])
        self.assertEqual(titles('?tag=ма'), [])                 # частичное совпадение не считается
        self.assertEqual(sorted(titles('?search=бухгалтерия')), ['Другое'])

    def test_too_many_tags_rejected(self):
        self.assertEqual(self.post_ad(tags=','.join(f't{i}' for i in range(11))).status_code, 400)

    def test_keep_revives_completed_ad_and_resets_reminder(self):
        ad_id = self.post_ad().data['id']
        self.api.post(f'/api/ads/{ad_id}/complete/', {}, format='json')
        ad = Ad.objects.get(id=ad_id)
        self.assertTrue(ad.is_completed)
        r = self.api.post(f'/api/ads/{ad_id}/keep/')
        self.assertEqual(r.status_code, 200, r.data)
        ad.refresh_from_db()
        self.assertFalse(ad.is_completed)
        self.assertTrue(ad.keep_listing)
        self.assertIsNone(ad.completion_requested_at)
        self.assertLess((timezone.now() - ad.last_reminder_at).total_seconds(), 60)

    def test_only_owner_can_keep(self):
        ad_id = self.post_ad().data['id']
        self.api.force_authenticate(self.premium)
        self.assertEqual(self.api.post(f'/api/ads/{ad_id}/keep/').status_code, 403)


class PriceHintsTests(PartABase):
    def test_hints_are_public_and_complete(self):
        r = self.api.get('/api/price-hints/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.data), 14)
        self.assertTrue(all({'title', 'price'} <= set(x) for x in r.data))
