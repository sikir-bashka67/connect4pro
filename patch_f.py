"""Демо-данные и README. Запуск из корня проекта: python patch_f.py"""
import pathlib, sys

SEED = r'''"""Демо-данные для показа и разработки. Только при DJANGO_DEBUG=True (или с --force)."""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from core.models import (
    AnalyticsEvent, Application, Category, Deal, DatabaseResource, Event, Financing, ForumPost, ForumTopic,
    Message, NotificationSubscription, Ad, ProviderProfile, ProviderService, User,
)

PASSWORD = 'demo12345'
PREFIX = 'demo_'

CATEGORIES = [('IT и цифровизация', 'it'), ('Сельское хозяйство', 'agro'), ('Производство', 'production'), ('Консалтинг и право', 'consulting')]

FINANCING = [
    ('Грант на развитие агробизнеса', 'grant', 'до 500 000 сом', 60, 'сельское хозяйство', 'агро,грант', 'agro',
     'Поддержка фермерских хозяйств: техника, теплицы, переработка. Нужен бизнес-план и подтверждение собственных вложений.'),
    ('Грант для IT-стартапов', 'grant', 'до 20 000 USD', 45, 'IT', 'it,стартап,грант', 'it',
     'Грант на запуск продукта: разработка, маркетинг, выход на рынок. Для команд до 3 лет на рынке.'),
    ('Грант для женщин-предпринимателей', 'grant', 'до 300 000 сом', 30, 'услуги', 'женщины,грант', 'consulting',
     'Финансирование малых проектов в сфере услуг и торговли, обучение в комплекте.'),
    ('Венчурный фонд: ранняя стадия', 'investment', 'от 50 000 до 250 000 USD', 90, 'IT', 'it,венчур,инвестиции', 'it',
     'Инвестиции в долю для технологических компаний с первыми продажами.'),
    ('Инвестиции в переработку (приём закрыт)', 'investment', 'от 100 000 USD', -10, 'производство', 'переработка,инвестиции', 'production',
     'Пример программы с истёкшим сроком: калькулятор покажет почти нулевой шанс.'),
]

EVENTS = [
    ('Курс: как написать заявку на грант', 'training', 14, 'Онлайн', 'Zoom, ссылка придёт после регистрации', 'любой', 'Практический курс на 3 вечера: структура заявки, бюджет, типичные ошибки.', 'consulting'),
    ('Бизнес-конференция Центральной Азии', 'conference', 30, 'Офлайн', 'Бишкек', 'любой', 'Выступления инвесторов и предпринимателей, нетворкинг.', 'consulting'),
    ('Стажировка на молочной ферме', 'internship', 60, 'Офлайн', 'Чуйская область', 'сельское хозяйство', 'Неделя практики на действующей ферме.', 'agro'),
    ('B2B-встреча производителей', 'b2b', 21, 'Офлайн', 'Бишкек, бизнес-центр', 'производство', 'Короткие встречи поставщиков и покупателей.', 'production'),
]

RESOURCES = [
    ('project', 'Проект: молочная ферма на 50 голов', 'сельское хозяйство', 'Описание проекта, смета оборудования и план окупаемости (демо-текст).', True, 'agro'),
    ('project', 'Проект: мобильное приложение доставки', 'IT', 'Описание продукта, этапы разработки и бюджет (демо-текст).', True, 'it'),
    ('business_plan', 'Бизнес-план: швейный цех', 'производство', 'Финансовая модель на 3 года, расчёт закупок и продаж (демо-текст).', True, 'production'),
    ('business_plan', 'Бизнес-план: кофейня «с собой»', 'услуги', 'Расчёт точки, расходы, прогноз выручки (демо-текст).', True, 'consulting'),
    ('case', 'Кейс: как стартап получил первый грант', 'IT', 'Открытый материал: что сработало в заявке, сколько времени заняло.', False, 'it'),
    ('donor', 'Донор: региональный фонд поддержки малого бизнеса', 'любой', 'Контакты, требования, календарь приёма заявок (демо-текст).', True, 'consulting'),
    ('investor', 'Инвестор: региональный венчурный фонд', 'IT', 'Профиль фонда, чеки, стадии (демо-текст).', True, 'it'),
    ('franchise', 'Франшиза: кофейня формата «с собой»', 'услуги', 'Условия франшизы, паушальный взнос, роялти (демо-текст).', True, 'consulting'),
]


class Command(BaseCommand):
    help = 'Создаёт демо-пользователей и демо-данные (повторный запуск ничего не дублирует). --clear удаляет их.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='удалить демо-данные')
        parser.add_argument('--force', action='store_true', help='разрешить запуск при DJANGO_DEBUG=False')

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts['force']:
            raise CommandError('Демо-данные создаются только при DJANGO_DEBUG=True (у них известные пароли). '
                               'Если вы точно знаете, что делаете: --force.')
        if opts['clear']:
            return self.clear()
        self.n = 0
        self.seed()
        self.stdout.write(self.style.SUCCESS(f'Готово. Создано новых записей: {self.n}.'))
        self.stdout.write(f'Пароль у всех демо-пользователей: {PASSWORD}')
        self.stdout.write('Логины: demo_admin, demo_premium_client, demo_client, demo_client2, demo_provider_premium, demo_provider')

    # ---- вспомогательное ----
    def make(self, model, lookup, defaults=None):
        obj, created = model.objects.get_or_create(defaults=defaults or {}, **lookup)
        if created:
            self.n += 1
        return obj

    def user(self, username, password=PASSWORD, **fields):
        u = User.objects.filter(username=username).first()
        if u:
            return u
        u = User.objects.create_user(username=username, password=password, **fields)
        self.n += 1
        return u

    def category(self, slug, name):
        c = Category.objects.filter(Q(slug=slug) | Q(name=name)).first()
        if not c:
            c = Category.objects.create(slug=slug, name=name)
            self.n += 1
        return c

    # ---- очистка ----
    def clear(self):
        deleted, _ = User.objects.filter(username__startswith=PREFIX).delete()
        Financing.objects.filter(title__in=[f[0] for f in FINANCING]).delete()
        Event.objects.filter(title__in=[e[0] for e in EVENTS]).delete()
        DatabaseResource.objects.filter(title__in=[r[1] for r in RESOURCES]).delete()
        self.stdout.write(self.style.SUCCESS('Демо-данные удалены (категории остались).'))

    # ---- создание ----
    def seed(self):
        now = timezone.now()
        cats = {slug: self.category(slug, name) for name, slug in CATEGORIES}
        premium_until = now + timedelta(days=365)

        self.user('demo_admin', email='demo_admin@example.com', role='admin', is_staff=True, is_superuser=True,
                  first_name='Админ', last_name='Демо')
        pc = self.user('demo_premium_client', email='demo_premium_client@example.com', role='client',
                       subscription='premium', premium_until=premium_until, first_name='Азамат', last_name='Токтогулов',
                       company_name='ОсОО «Алтын Таш»', phone='+996 700 100 200', region='Бишкек',
                       business_sector='IT', employees_count=12, annual_turnover='up_to_5m',
                       what_i_offer='Разработка и поддержка веб-сервисов.', what_i_seek='Инвестор для запуска нового продукта.',
                       consent_public_offer=True)
        c1 = self.user('demo_client', email='demo_client@example.com', role='client', first_name='Айгерим',
                       last_name='Сыдыкова', company_name='Швейный цех «Нур»', phone='+996 555 300 400',
                       region='Чуйская область', business_sector='производство', employees_count=8,
                       annual_turnover='up_to_1m', what_i_offer='Пошив спецодежды и текстиля.',
                       what_i_seek='Клиенты, сайт, помощь с грантом.', consent_public_offer=True)
        c2 = self.user('demo_client2', email='demo_client2@example.com', role='client', first_name='Бакыт',
                       last_name='Асанов', company_name='Ферма «Ак-Суу»', phone='+996 770 500 600', region='Иссык-Куль',
                       business_sector='сельское хозяйство', employees_count=5, annual_turnover='up_to_500k',
                       what_i_offer='Молочная продукция.', what_i_seek='Грант на оборудование.', consent_public_offer=True)
        pp = self.user('demo_provider_premium', email='demo_provider_premium@example.com', role='provider',
                       subscription='premium', premium_until=premium_until, first_name='Нурлан', last_name='Эсенов')
        pf = self.user('demo_provider', email='demo_provider@example.com', role='provider', first_name='Айдай',
                       last_name='Бекова')

        prof_p = self.make(ProviderProfile, {'provider': pp}, dict(
            company_name='Digital Bishkek', activity='Веб-разработка и маркетинг', founded_year=2018,
            manager_name='Эсенов Нурлан', description='Команда из 15 человек: сайты, магазины, продвижение.',
            services_description='Сайты, интернет-магазины, SEO, реклама.', phone='+996 700 900 100',
            email='hello@digital-bishkek.example', address='Бишкек, ул. Токтогула, 1', website='https://digital-bishkek.example'))
        self.make(ProviderProfile, {'provider': pf}, dict(
            company_name='Финансовый консалтинг «Баланс»', activity='Бухгалтерия и юридические услуги', founded_year=2015,
            manager_name='Бекова Айдай', description='Бухгалтерское сопровождение и регистрация компаний.',
            services_description='Бухгалтерия, регистрация ОсОО, налоги.', phone='+996 555 700 800',
            email='info@balance.example', address='Бишкек, пр. Чуй, 100'))

        svc1 = self.make(ProviderService, {'provider': pp, 'title': 'Разработка сайтов и интернет-магазинов'}, dict(
            description='Сайт под ключ: дизайн, разработка, запуск. Срок от 3 недель.', price=45000, currency='KGS',
            tags='сайт,веб,магазин', category=cats['it']))
        svc2 = self.make(ProviderService, {'provider': pp, 'title': 'Бизнес-план под грант'}, dict(
            description='Подготовим бизнес-план и финансовую модель под требования донора.', price=20000, currency='KGS',
            tags='грант,бизнес-план', category=cats['consulting']))
        self.make(ProviderService, {'provider': pf, 'title': 'Бухгалтерское сопровождение'}, dict(
            description='Ведение учёта и отчётности для малого бизнеса.', price=12000, currency='KGS',
            tags='бухгалтерия,налоги', category=cats['consulting']))
        self.make(ProviderService, {'provider': pf, 'title': 'Регистрация ОсОО под ключ'}, dict(
            description='Документы, печать, счёт в банке.', price=8000, currency='KGS',
            tags='регистрация,юридические', category=cats['consulting']))

        self.make(Ad, {'author': c1, 'title': 'Нужен сайт для швейного цеха'}, dict(
            listing_type='request', description='Нужен сайт-визитка с каталогом и формой заявки.', price=60000,
            currency='KGS', tags='сайт,веб,производство', category=cats['it'], what_i_offer_optional='Скидки на пошив для вашей команды.'))
        self.make(Ad, {'author': pc, 'title': 'Продаю 30% доли в кофейне, Бишкек'}, dict(
            listing_type='sell_share', description='Действующая кофейня, выручка стабильная, нужен партнёр для второй точки.',
            price=1500000, currency='KGS', tags='доля,кофейня,бизнес', category=cats['consulting']))
        self.make(Ad, {'author': pc, 'title': 'Куплю долю в IT-компании'}, dict(
            listing_type='buy_share', description='Рассматриваю долю в продуктовой IT-команде с выручкой.', price=20000,
            currency='USD', tags='доля,it,инвестиции', category=cats['it']))
        self.make(Ad, {'author': c2, 'title': 'Нужна помощь с заявкой на грант'}, dict(
            listing_type='request', description='Ферма, нужен бизнес-план и оформление заявки на грант.', price=15000,
            currency='KGS', tags='грант,агро,бизнес-план', category=cats['agro']))
        self.make(Ad, {'author': c1, 'title': 'Ищем бухгалтера на аутсорс'}, dict(
            listing_type='request', description='Небольшой цех, нужен учёт и отчётность раз в месяц.', price=25000,
            currency='KGS', tags='бухгалтерия', category=cats['consulting']))

        fins = {}
        for title, kind, amount, days, sector, tags, cat, text in FINANCING:
            fins[title] = self.make(Financing, {'title': title}, dict(
                financing_type=kind, amount_description=amount, deadline=(now + timedelta(days=days)).date(),
                description=text, sector=sector, tags=tags, category=cats[cat]))
        for title, kind, days, fmt, place, sector, text, cat in EVENTS:
            self.make(Event, {'title': title}, dict(
                event_type=kind, date_and_time=now + timedelta(days=days), format=fmt, location=place,
                description=text, sector=sector, category=cats[cat]))
        for kind, title, sector, content, premium_only, cat in RESOURCES:
            self.make(DatabaseResource, {'title': title}, dict(
                resource_type=kind, sector=sector, file_or_content=content, is_premium_only=premium_only, category=cats[cat]))

        topics = [
            ('Как подготовить заявку на грант с первого раза?', 'grants', c2,
             [(c1, 'Начните с чёткого бюджета: донор смотрит на него в первую очередь.'),
              (pp, 'Могу помочь с бизнес-планом, пишите в личные сообщения.')]),
            ('Оформление договора при продаже доли', 'legal', pc,
             [(pf, 'Обязательно нотариальное удостоверение и оценка доли.')]),
            ('Где искать инвестора на ранней стадии?', 'investments', c1, []),
        ]
        for title, kind, author, posts in topics:
            topic = self.make(ForumTopic, {'title': title}, dict(topic_type=kind, author=author))
            for who, text in posts:
                self.make(ForumPost, {'topic': topic, 'author': who, 'text': text})

        self.make(Application, {'client': c1, 'provider_service': svc1}, dict(status='approved', message='Нужен сайт для цеха.'))
        self.make(Application, {'client': c2, 'provider_service': svc2}, dict(status='pending', message='Готовим заявку на грант.'))
        self.make(Application, {'client': c1, 'financing': fins['Грант для IT-стартапов']}, dict(status='pending', message='Интересует программа.'))

        self.make(Deal, {'client': c1, 'provider': pp, 'provider_service': svc1}, dict(
            status='completed', amount=45000, completed_at=now - timedelta(days=2)))
        self.make(Deal, {'client': c2, 'provider': pp, 'provider_service': svc2}, dict(status='started', amount=20000))

        self.make(Message, {'sender': c1, 'recipient': pp, 'text': 'Здравствуйте! Сколько займёт сайт-визитка?'})
        self.make(Message, {'sender': pp, 'recipient': c1, 'text': 'Добрый день! Около трёх недель, пришлю смету.'})

        self.make(NotificationSubscription, {'user': c1}, dict(
            email=c1.email, financing_updates=True, sector_updates=True, sector='производство', active=True))

        if not AnalyticsEvent.objects.filter(object_type='provider', object_id=prof_p.id).exists():
            for i in range(14):
                AnalyticsEvent.objects.create(event_type='click', object_type='provider', object_id=prof_p.id)
            for i in range(3):
                AnalyticsEvent.objects.create(event_type='share', object_type='provider', object_id=prof_p.id, source='telegram')
            self.n += 17
        if not AnalyticsEvent.objects.filter(event_type='visit').exists():
            for i, src in enumerate(['direct'] * 12 + ['google'] * 8 + ['telegram'] * 6 + ['facebook'] * 4):
                AnalyticsEvent.objects.create(event_type='visit', source=src)
            self.n += 30
'''

TESTS = r'''"""Демо-данные: seed_demo."""
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
'''

README = r'''

## Демо-данные

Для показа и проверки интерфейса (только при `DJANGO_DEBUG=True`):

```powershell
python manage.py seed_demo
```

Создаются 6 пользователей, профили и услуги провайдеров, объявления (запросы, продажа и покупка доли), гранты и инвестиции, мероприятия, материалы баз данных, темы форума, заявки, сделки, сообщения и немного аналитики. Повторный запуск ничего не дублирует.

Пароль у всех демо-пользователей: `demo12345`.

| Логин | Кто |
|---|---|
| `demo_admin` | Администратор: раздел «Аналитика» |
| `demo_premium_client` | Клиент с Premium |
| `demo_client`, `demo_client2` | Клиенты без подписки |
| `demo_provider_premium` | Провайдер с Premium: «Аналитика кабинета» с цифрами |
| `demo_provider` | Провайдер без подписки |

Удалить демо-данные: `python manage.py seed_demo --clear`. Команда отказывается работать при `DJANGO_DEBUG=False`, потому что у демо-пользователей известные пароли. Не запускайте её на боевом сайте.

## Рассылка о грантах и инвестициях

Пользователь включает рассылку в «Аккаунт»: все новые программы или только свой сектор. Письма отправляет команда:

```powershell
python manage.py send_grant_digests
```

Запускайте её раз в сутки через планировщик Windows / cron. Ключ `--dry-run` только считает, не отправляя писем. В каждом письме есть ссылка «Отписаться». Для реальной отправки задайте SMTP (`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`) и `SITE_URL` в `.env`, иначе письма попадают в консоль, а ссылки ведут на локальный адрес.

## Аналитика

* Администратору: раздел «Аналитика» (посетители, пользователи, сделки, оплаты, источники, регионы, популярное объявление).
* Premium-провайдеру: «Аналитика кабинета» в аккаунте (просмотры профиля, заявки и сделки по услугам), `GET /api/analytics/provider/`.

## Тесты

```powershell
python manage.py test core
```
'''

def wr(p, s):
    pp = pathlib.Path(p); pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(s, encoding='utf-8', newline='\n')

if not pathlib.Path('core/models.py').exists():
    sys.exit('Запускайте из корня проекта (там, где manage.py).')
cmd = pathlib.Path('core/management/commands/seed_demo.py')
if cmd.exists():
    sys.exit('seed_demo.py уже есть, похоже, патч уже применён. Ничего не делаю.')
readme = pathlib.Path('README.md')
text = readme.read_text(encoding='utf-8') if readme.exists() else '# Connect4Pro\n'
if '## Демо-данные' not in text:
    wr('README.md', text.rstrip('\n') + '\n' + README)
wr(str(cmd), SEED)
wr('core/test_part_f.py', TESTS)
print('Готово. Дальше: python manage.py test core.test_part_f, затем python manage.py seed_demo')
