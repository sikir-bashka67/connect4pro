"""Блок C: калькулятор под конкретную программу, аналитика (название топ-объявления, источники трафика, доступ)."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Ad, AnalyticsEvent, Event, Financing, User


class PartCBase(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        mk = User.objects.create_user
        self.premium = mk(username='pr', password='pass12345', role='client', email='pr@x.kg', subscription='premium')
        self.client_u = mk(username='cl', password='pass12345', role='client', email='cl@x.kg')
        self.admin = mk(username='adm', password='pass12345', role='admin', email='a@x.kg', is_staff=True)


class CalculatorFinancingTests(PartCBase):
    payload = {'annual_turnover': 'up_to_100k', 'employees_count': 1, 'sector': 'IT'}  # базовый балл 50

    def setUp(self):
        super().setUp()
        self.api.force_authenticate(self.premium)

    def program(self, **kw):
        base = dict(title='Грант', financing_type='grant', amount_description='1', description='d')
        base.update(kw)
        return Financing.objects.create(**base)

    def test_without_program_result_is_unchanged(self):
        r = self.api.post('/api/calculator/', self.payload, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['calculated_probability_percent'], 50)
        self.assertNotIn('financing', r.data)

    def test_sector_match_and_mismatch(self):
        it = self.program(title='IT грант', sector='IT')
        farm = self.program(title='Агро', sector='с/х')
        r = self.api.post('/api/calculator/', dict(self.payload, financing=it.id), format='json')
        self.assertEqual(r.data['calculated_probability_percent'], 60)
        self.assertEqual(r.data['financing'], {'id': it.id, 'title': 'IT грант'})
        r = self.api.post('/api/calculator/', dict(self.payload, financing=farm.id), format='json')
        self.assertEqual(r.data['calculated_probability_percent'], 40)

    def test_investment_bonus_for_big_turnover(self):
        inv = self.program(financing_type='investment')
        r = self.api.post('/api/calculator/', dict(self.payload, annual_turnover='up_to_5m', financing=inv.id), format='json')
        self.assertEqual(r.data['calculated_probability_percent'], 80)  # 50 + 25 оборот + 5 инвестиции

    def test_expired_program_caps_probability(self):
        old = self.program(deadline=timezone.localdate() - timedelta(days=1))
        r = self.api.post('/api/calculator/', dict(self.payload, financing=old.id), format='json')
        self.assertEqual(r.data['calculated_probability_percent'], 5)
        self.assertIn('истёк', r.data['recommendation'])

    def test_unknown_program_rejected_and_payment_not_burned(self):
        self.api.force_authenticate(None)
        for bad in (99999, 'abc'):
            r = self.api.post('/api/calculator/', dict(self.payload, financing=bad), format='json')
            self.assertEqual(r.status_code, 400)  # не 402: ошибка формы проверяется до оплаты


class AnalyticsTests(PartCBase):
    def test_most_clicked_title_traffic_and_access(self):
        ad = Ad.objects.create(title='Горячее', description='d', price=1, author=self.client_u)
        self.api.get(f'/api/ads/{ad.id}/')
        self.api.post('/api/analytics/track/', {'event_type': 'traffic', 'source': 'instagram'}, format='json')
        self.api.post('/api/analytics/track/', {'event_type': 'visit'}, format='json')
        self.api.post('/api/analytics/track/', {'event_type': 'share', 'object_type': 'event', 'object_id': 1, 'source': 'telegram'}, format='json')
        self.assertEqual(self.api.get('/api/analytics/').status_code, 401)
        self.api.force_authenticate(self.client_u)
        self.assertEqual(self.api.get('/api/analytics/').status_code, 403)
        self.api.force_authenticate(self.admin)
        d = self.api.get('/api/analytics/').data
        self.assertEqual(d['most_clicked_ad_title'], 'Горячее')
        self.assertEqual(d['traffic_sources'][0]['source'], 'instagram')
        self.assertEqual(d['visitors_all_time'], 1)
        self.assertEqual(d['shares'], 1)

    def test_no_clicks_gives_empty_title(self):
        self.api.force_authenticate(self.admin)
        d = self.api.get('/api/analytics/').data
        self.assertIsNone(d['most_clicked_ad_title'])


class SearchFilterTests(PartCBase):
    def test_financing_tabs_search_and_ordering(self):
        Financing.objects.create(title='Грант фермерам', financing_type='grant', amount_description='1', description='d', tags='агро')
        Financing.objects.create(title='Инвестор в IT', financing_type='investment', amount_description='1', description='d')
        self.assertEqual(self.api.get('/api/financing/?financing_type=grant').data['count'], 1)
        self.assertEqual(self.api.get('/api/financing/?financing_type=investment').data['count'], 1)
        self.assertEqual(self.api.get('/api/financing/?search=агро').data['count'], 1)

    def test_events_search_and_type(self):
        Event.objects.create(title='Тренинг по продажам', event_type='training', date_and_time=timezone.now(), description='d', tags='продажи')
        Event.objects.create(title='B2B встреча', event_type='b2b', date_and_time=timezone.now(), description='d')
        self.assertEqual(self.api.get('/api/events/?event_type=training').data['count'], 1)
        self.assertEqual(self.api.get('/api/events/?search=продажи').data['count'], 1)

    def test_completed_ads_can_be_hidden_from_list(self):
        Ad.objects.create(title='Живое', description='d', price=1, author=self.client_u)
        Ad.objects.create(title='Закрытое', description='d', price=1, author=self.client_u, is_completed=True)
        r = self.api.get('/api/ads/?is_completed=false')
        self.assertEqual([x['title'] for x in r.data['results']], ['Живое'])

    def test_forum_section_filter_and_search(self):
        from .models import ForumTopic
        ForumTopic.objects.create(title='Как получить грант', topic_type='grants', author=self.client_u)
        ForumTopic.objects.create(title='Юридический вопрос', topic_type='legal', author=self.client_u)
        self.assertEqual(self.api.get('/api/forum/topics/?topic_type=grants').data['count'], 1)
        self.assertEqual(self.api.get('/api/forum/topics/?search=Юридический').data['count'], 1)

    def test_directory_search_by_offer(self):
        User.objects.create_user(username='o1', password='pass12345', role='client', email='o1@x.kg',
                                 what_i_offer='Бухгалтерия', consent_public_offer=True)
        User.objects.create_user(username='o2', password='pass12345', role='client', email='o2@x.kg',
                                 what_i_offer='Дизайн', consent_public_offer=True)
        r = self.api.get('/api/clients/directory/?search=Бухгалтерия')
        self.assertEqual([x['what_i_offer'] for x in r.data['results']], ['Бухгалтерия'])
