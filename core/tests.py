from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from . import payments
from .models import (
    User, Category, Ad, ProviderService, ProviderProfile, ForumTopic,
    DatabaseResource, ResourceUnlock, PaymentTransaction,
)


class BaseCase(TestCase):
    def setUp(self):
        cache.clear()  # сброс счётчиков троттлинга между тестами
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


# ============================ ЭТАП 2 =========================================
def pay(user, purpose):
    """Создаёт и сразу оплачивает платёж (имитация успешной оплаты шлюзом)."""
    tx = payments.create_transaction(user, purpose)
    return payments.mark_paid(tx)


STUB_ON = dict(PAYMENT_GATEWAY='stub', PAYMENTS_STUB_ENABLED=True)
PAYBOX_ON = dict(PAYMENT_GATEWAY='paybox', PAYBOX_MERCHANT_ID='m1', PAYBOX_SECRET_KEY='s3cret')


class PaymentTests(BaseCase):
    @override_settings(**STUB_ON)
    def test_checkout_amount_comes_from_server(self):
        self.api.force_authenticate(self.client_u)
        r = self.api.post('/api/payments/checkout/', {'purpose': 'premium', 'amount': '1'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Decimal(r.data['amount']), settings.PRICES_KGS['premium'])
        self.assertEqual(r.data['status'], 'pending')
        self.assertTrue(r.data['access_token'])

    @override_settings(**STUB_ON)
    def test_guest_can_only_buy_calculator(self):
        r = self.api.post('/api/payments/checkout/', {'purpose': 'premium'}, format='json')
        self.assertIn(r.status_code, (401, 403))
        r = self.api.post('/api/payments/checkout/', {'purpose': 'calculator'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(r.data['user'])

    @override_settings(**STUB_ON)
    def test_unknown_purpose_rejected(self):
        self.api.force_authenticate(self.client_u)
        for bad in ('hack', None, ['premium']):
            r = self.api.post('/api/payments/checkout/', {'purpose': bad}, format='json')
            self.assertEqual(r.status_code, 400)

    @override_settings(**STUB_ON)
    def test_packs_require_premium_and_calculator_is_free_for_premium(self):
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.post('/api/payments/checkout/', {'purpose': 'pack_project'}, format='json').status_code, 403)
        self.api.force_authenticate(self.premium)
        self.assertEqual(self.api.post('/api/payments/checkout/', {'purpose': 'pack_project'}, format='json').status_code, 201)
        self.assertEqual(self.api.post('/api/payments/checkout/', {'purpose': 'calculator'}, format='json').status_code, 400)

    @override_settings(**STUB_ON)
    def test_stub_pay_needs_correct_token(self):
        tx = self.api.post('/api/payments/checkout/', {'purpose': 'calculator'}, format='json').data
        url = f'/api/payments/{tx["id"]}/stub-pay/'
        self.assertEqual(self.api.post(url, {'access_token': 'wrong'}, format='json').status_code, 403)
        self.assertEqual(self.api.post(url, {}, format='json').status_code, 403)
        r = self.api.post(url, {'access_token': tx['access_token']}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'paid')

    @override_settings(PAYMENT_GATEWAY='stub', PAYMENTS_STUB_ENABLED=False)
    def test_stub_is_unavailable_when_disabled(self):
        tx = payments.create_transaction(None, 'calculator')
        r = self.api.post(f'/api/payments/{tx.id}/stub-pay/', {'access_token': tx.access_token}, format='json')
        self.assertEqual(r.status_code, 404)
        r = self.api.post('/api/payments/checkout/', {'purpose': 'calculator'}, format='json')
        self.assertEqual(r.status_code, 502)

    def test_premium_payment_extends_period_and_is_idempotent(self):
        tx = payments.create_transaction(self.client_u, 'premium')
        payments.mark_paid(tx)
        self.client_u.refresh_from_db()
        first = self.client_u.premium_until
        self.assertEqual(self.client_u.subscription, 'premium')
        self.assertGreater(first, timezone.now() + timedelta(days=settings.PREMIUM_PERIOD_DAYS - 1))
        payments.mark_paid(tx)  # повторное уведомление шлюза ничего не меняет
        self.client_u.refresh_from_db()
        self.assertEqual(self.client_u.premium_until, first)
        pay(self.client_u, 'premium')  # продление добавляет ещё период
        self.client_u.refresh_from_db()
        self.assertGreater(self.client_u.premium_until, first + timedelta(days=settings.PREMIUM_PERIOD_DAYS - 1))

    def test_payments_are_read_only_and_admin_can_confirm(self):
        tx = payments.create_transaction(self.client_u, 'premium')
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.post('/api/payments/', {'amount': '1'}, format='json').status_code, 405)
        self.assertEqual(self.api.get('/api/payments/').data['count'], 1)
        self.assertEqual(self.api.post(f'/api/payments/{tx.id}/confirm/').status_code, 403)
        self.api.force_authenticate(self.admin)
        r = self.api.post(f'/api/payments/{tx.id}/confirm/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'paid')

    @override_settings(**PAYBOX_ON)
    def test_paybox_webhook_signature_amount_and_result(self):
        tx = payments.create_transaction(self.client_u, 'premium')
        base = {'pg_order_id': str(tx.id), 'pg_payment_id': '777', 'pg_amount': f'{tx.amount:.2f}', 'pg_result': '1'}
        url = '/api/payments/webhook/paybox/'

        bad = dict(base, pg_sig='deadbeef')
        self.assertEqual(self.api.post(url, bad).status_code, 403)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'pending')

        wrong_amount = dict(base, pg_amount='1.00')
        wrong_amount['pg_sig'] = payments.paybox_signature('paybox', wrong_amount, 's3cret')
        r = self.api.post(url, wrong_amount)
        self.assertIn(b'rejected', r.content)
        tx.refresh_from_db()
        self.assertEqual(tx.status, 'pending')

        good = dict(base)
        good['pg_sig'] = payments.paybox_signature('paybox', good, 's3cret')
        r = self.api.post(url, good)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'<pg_status>ok</pg_status>', r.content)
        tx.refresh_from_db()
        self.client_u.refresh_from_db()
        self.assertEqual((tx.status, tx.external_id, self.client_u.subscription), ('paid', '777', 'premium'))

    def test_paybox_webhook_closed_in_stub_mode(self):
        self.assertEqual(self.api.post('/api/payments/webhook/paybox/', {'pg_order_id': '1'}).status_code, 404)


class CalculatorTests(BaseCase):
    payload = {'annual_turnover': 'up_to_5m', 'employees_count': 10, 'sector': 'IT'}

    def test_guest_and_freemium_must_pay(self):
        r = self.api.post('/api/calculator/', self.payload, format='json')
        self.assertEqual(r.status_code, 402)
        self.assertEqual(r.data['price'], str(settings.PRICES_KGS['calculator']))
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.post('/api/calculator/', self.payload, format='json').status_code, 402)

    def test_paid_calculation_is_single_use(self):
        tx = pay(None, 'calculator')
        body = dict(self.payload, payment_id=tx.id, access_token=tx.access_token)
        r = self.api.post('/api/calculator/', body, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['calculated_probability_percent'], 95)
        self.assertEqual(self.api.post('/api/calculator/', body, format='json').status_code, 402)

    def test_wrong_token_unpaid_or_foreign_purpose_payment_rejected(self):
        paid = pay(None, 'calculator')
        unpaid = payments.create_transaction(None, 'calculator')
        other_purpose = pay(self.client_u, 'premium')
        cases = [
            dict(payment_id=paid.id, access_token='wrong'),
            dict(payment_id=unpaid.id, access_token=unpaid.access_token),
            dict(payment_id=other_purpose.id, access_token=other_purpose.access_token),
            dict(payment_id='abc', access_token='x'),
        ]
        for extra in cases:
            r = self.api.post('/api/calculator/', dict(self.payload, **extra), format='json')
            self.assertEqual(r.status_code, 402, extra)
        paid.refresh_from_db()
        self.assertIsNone(paid.consumed_at)

    def test_premium_and_admin_use_it_free(self):
        for who in (self.premium, self.admin):
            self.api.force_authenticate(who)
            self.assertEqual(self.api.post('/api/calculator/', self.payload, format='json').status_code, 200)

    def test_invalid_input_does_not_burn_payment(self):
        tx = pay(None, 'calculator')
        body = {'annual_turnover': 'bogus', 'payment_id': tx.id, 'access_token': tx.access_token}
        self.assertEqual(self.api.post('/api/calculator/', body, format='json').status_code, 400)
        tx.refresh_from_db()
        self.assertIsNone(tx.consumed_at)


class ResourceQuotaTests(BaseCase):
    def setUp(self):
        super().setUp()
        mk = DatabaseResource.objects.create
        self.projects = [mk(resource_type='project', title=f'P{i}', sector='IT', file_or_content=f'secret-p{i}')
                         for i in range(12)]
        self.plans = [mk(resource_type='business_plan', title=f'B{i}', sector='IT', file_or_content=f'secret-b{i}')
                      for i in range(3)]
        self.donor = mk(resource_type='donor', title='Donor', sector='IT', file_or_content='secret-donor')
        self.free_project = mk(resource_type='project', title='Free', sector='IT', file_or_content='open',
                               is_premium_only=False)

    def unlock(self, res):
        return self.api.post(f'/api/database-resources/{res.id}/unlock/')

    def quota(self):
        return self.api.get('/api/database-resources/quota/').data

    def test_freemium_and_guest_see_only_free_materials(self):
        for who in (None, self.client_u):
            self.api.force_authenticate(who)
            rows = self.api.get('/api/database-resources/?resource_type=project').data['results']
            self.assertEqual([x['title'] for x in rows], ['Free'])
            self.assertEqual(rows[0]['file_or_content'], 'open')

    def test_premium_list_hides_content_until_unlock(self):
        self.api.force_authenticate(self.premium)
        rows = self.api.get('/api/database-resources/?resource_type=project').data['results']
        self.assertEqual(len(rows), 13)
        for row in rows:
            if row['title'] != 'Free':
                self.assertNotIn('file_or_content', row)
                self.assertFalse(row['content_available'])
        donor = self.api.get('/api/database-resources/?resource_type=donor').data['results'][0]
        self.assertEqual(donor['file_or_content'], 'secret-donor')

    def test_unlock_reveals_content_and_uses_one_slot(self):
        self.api.force_authenticate(self.premium)
        r = self.unlock(self.projects[0])
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['file_or_content'], 'secret-p0')
        q = self.quota()
        self.assertEqual((q['project']['included_used'], q['project']['included_left']), (1, 9))
        self.assertEqual(q['business_plan']['included_left'], 10)
        detail = self.api.get(f'/api/database-resources/{self.projects[0].id}/').data
        self.assertEqual(detail['file_or_content'], 'secret-p0')
        other = self.api.get(f'/api/database-resources/{self.projects[1].id}/').data
        self.assertNotIn('file_or_content', other)

    def test_repeat_unlock_is_free(self):
        self.api.force_authenticate(self.premium)
        self.unlock(self.projects[0])
        self.unlock(self.projects[0])
        self.assertEqual(self.quota()['project']['included_used'], 1)

    def test_eleventh_project_requires_pack_but_plans_have_own_limit(self):
        self.api.force_authenticate(self.premium)
        for p in self.projects[:10]:
            self.assertEqual(self.unlock(p).status_code, 200)
        r = self.unlock(self.projects[10])
        self.assertEqual(r.status_code, 402)
        self.assertEqual(r.data['purchase'], 'pack_project')
        self.assertEqual(self.unlock(self.plans[0]).status_code, 200)

    def test_pack_adds_fifty_places(self):
        self.api.force_authenticate(self.premium)
        for p in self.projects[:10]:
            self.unlock(p)
        pay(self.premium, 'pack_project')
        self.assertEqual(self.unlock(self.projects[10]).status_code, 200)
        q = self.quota()['project']
        self.assertEqual((q['pack_total'], q['pack_used'], q['pack_left'], q['included_left']), (50, 1, 49, 0))
        self.assertEqual(ResourceUnlock.objects.get(user=self.premium, resource=self.projects[10]).source, 'pack')

    def test_freemium_cannot_unlock(self):
        self.api.force_authenticate(self.client_u)
        self.assertIn(self.unlock(self.projects[0]).status_code, (403, 404))
        self.assertEqual(ResourceUnlock.objects.count(), 0)

    def test_guest_cannot_use_quota_endpoints(self):
        self.assertIn(self.api.get('/api/database-resources/quota/').status_code, (401, 403))
        self.assertIn(self.unlock(self.projects[0]).status_code, (401, 403))

    def test_lapsed_premium_keeps_only_pack_items(self):
        self.api.force_authenticate(self.premium)
        for p in self.projects[:10]:
            self.unlock(p)
        pay(self.premium, 'pack_project')
        self.unlock(self.projects[10])
        self.premium.premium_until = timezone.now() - timedelta(days=1)
        self.premium.save()
        kept = self.api.get(f'/api/database-resources/{self.projects[10].id}/')
        self.assertEqual(kept.status_code, 200)
        self.assertEqual(kept.data['file_or_content'], 'secret-p10')
        self.assertEqual(self.api.get(f'/api/database-resources/{self.projects[0].id}/').status_code, 404)

    def test_other_types_need_premium_but_no_unlock(self):
        self.api.force_authenticate(self.premium)
        r = self.unlock(self.donor)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['file_or_content'], 'secret-donor')
        self.assertEqual(ResourceUnlock.objects.count(), 0)

    def test_admin_sees_everything(self):
        self.api.force_authenticate(self.admin)
        r = self.api.get(f'/api/database-resources/{self.projects[5].id}/')
        self.assertEqual(r.data['file_or_content'], 'secret-p5')


class AdPriorityAndBumpTests(BaseCase):
    def ad(self, author, kind='request', title='x'):
        return Ad.objects.create(title=title, description='d', price=1, author=author, listing_type=kind)

    def order(self):
        return [x['id'] for x in self.api.get('/api/ads/').data['results']]

    def test_premium_share_ads_come_first(self):
        premium_share = self.ad(self.premium, 'sell_share')
        free_share = self.ad(self.client_u, 'sell_share')
        premium_plain = self.ad(self.premium, 'request')
        self.assertEqual(self.order(), [premium_share.id, premium_plain.id, free_share.id])

    def test_lapsed_premium_loses_priority(self):
        premium_share = self.ad(self.premium, 'buy_share')
        free_share = self.ad(self.client_u, 'sell_share')
        self.premium.premium_until = timezone.now() - timedelta(days=1)
        self.premium.save()
        self.assertEqual(self.order(), [free_share.id, premium_share.id])

    def test_client_can_create_share_ad_and_type_is_validated(self):
        self.api.force_authenticate(self.client_u)
        body = {'title': 'Продам долю', 'description': 'd', 'price': '1000', 'listing_type': 'sell_share'}
        r = self.api.post('/api/ads/', body, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Ad.objects.get(id=r.data['id']).listing_type, 'sell_share')
        self.assertEqual(self.api.post('/api/ads/', dict(body, listing_type='nope'), format='json').status_code, 400)

    def test_manual_bump_is_premium_only_and_moves_ad_up(self):
        old = self.ad(self.premium, title='old')
        new = self.ad(self.client_u, title='new')
        self.assertEqual(self.order(), [new.id, old.id])
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.post(f'/api/ads/{new.id}/bump/').status_code, 403)
        self.api.force_authenticate(self.premium)
        self.assertEqual(self.api.post(f'/api/ads/{old.id}/bump/').status_code, 200)
        self.assertEqual(self.order(), [old.id, new.id])
        old.refresh_from_db()
        self.assertFalse(old.auto_bump)  # ручное поднятие не включает автоподнятие

    def test_auto_bump_toggle(self):
        mine = self.ad(self.client_u)
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.post(f'/api/ads/{mine.id}/auto-bump/', {'enabled': True}, format='json').status_code, 403)
        self.assertEqual(self.api.post(f'/api/ads/{mine.id}/auto-bump/', {'enabled': False}, format='json').status_code, 200)
        prem = self.ad(self.premium)
        self.api.force_authenticate(self.premium)
        self.assertEqual(self.api.post(f'/api/ads/{prem.id}/auto-bump/', {'enabled': True}, format='json').status_code, 200)
        prem.refresh_from_db()
        self.assertTrue(prem.auto_bump)
        self.api.force_authenticate(self.client2)
        self.assertEqual(self.api.post(f'/api/ads/{prem.id}/auto-bump/', {'enabled': False}, format='json').status_code, 403)

    def test_scheduled_auto_bump_only_for_active_premium_and_respects_interval(self):
        lapsed = User.objects.create_user(username='lapsed', password='pass12345', role='client',
                                          subscription='premium', premium_until=timezone.now() - timedelta(days=2))
        two_days_ago = timezone.now() - timedelta(days=2)
        recent = timezone.now() - timedelta(hours=1)
        due = self.ad(self.premium, title='due')
        free = self.ad(self.client_u, title='free')
        gone = self.ad(lapsed, title='lapsed')
        fresh = self.ad(self.premium, title='fresh')
        Ad.objects.filter(pk__in=[due.pk, free.pk, gone.pk]).update(auto_bump=True, created_at=two_days_ago)
        Ad.objects.filter(pk=fresh.pk).update(auto_bump=True, created_at=two_days_ago, last_bumped_at=recent)

        call_command('process_platform_jobs', stdout=StringIO())
        for ad in (due, free, gone, fresh):
            ad.refresh_from_db()
        self.assertIsNotNone(due.last_bumped_at)
        self.assertIsNone(free.last_bumped_at)
        self.assertIsNone(gone.last_bumped_at)
        self.assertEqual(fresh.last_bumped_at, recent)

        first = due.last_bumped_at
        call_command('process_platform_jobs', stdout=StringIO())
        due.refresh_from_db()
        self.assertEqual(due.last_bumped_at, first)  # интервал ещё не прошёл
