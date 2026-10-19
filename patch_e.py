"""Рассылка о грантах и инвестициях. Запуск из корня проекта: python patch_e.py"""
import pathlib, sys

MAILING = r'''"""Рассылка о новых программах финансирования (гранты и инвестиции)."""
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.utils import timezone

from .models import Financing, NotificationSubscription

SALT = 'c4p-unsubscribe'
MAX_ITEMS = 20        # сколько программ показываем в одном письме
MAX_BACKLOG_DAYS = 30  # за какой максимум отправляем накопившееся


def unsubscribe_token(sub):
    return signing.dumps({'sub': sub.pk}, salt=SALT)


def subscription_from_token(token):
    try:
        data = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return None
    return NotificationSubscription.objects.filter(pk=data.get('sub')).first()


def items_for(sub, until):
    """Новые программы для подписчика: все (financing_updates) или только его сектора (sector_updates)."""
    since = max(sub.last_notified_at, until - timedelta(days=MAX_BACKLOG_DAYS))
    new = Financing.objects.filter(created_at__gt=since, created_at__lte=until).order_by('created_at')
    if sub.financing_updates:
        return list(new)
    sector = (sub.sector or '').strip()
    if sub.sector_updates and sector:
        return list(new.filter(sector__icontains=sector))
    return []


def build_message(sub, items):
    base = settings.SITE_URL
    shown = items[:MAX_ITEMS]
    lines = ['Здравствуйте!', '', 'Новые программы финансирования на Connect4Pro:', '']
    for f in shown:
        deadline = f.deadline.strftime('%d.%m.%Y') if f.deadline else 'без срока'
        lines += [f'- [{f.get_financing_type_display()}] {f.title}',
                  f'  {f.amount_description}. Дедлайн: {deadline}',
                  f'  {base}/#fin/{f.pk}', '']
    if len(items) > len(shown):
        lines += [f'И ещё программ: {len(items) - len(shown)}. Смотрите на сайте: {base}/#financing', '']
    lines += ['Отписаться от рассылки:', f'{base}/api/notifications/unsubscribe/?token={unsubscribe_token(sub)}']
    subject = f'Connect4Pro: новых программ финансирования: {len(items)}'
    return subject, '\n'.join(lines)


def send_financing_digests(now=None, dry_run=False):
    """Отправляет по одному письму каждому активному подписчику. Возвращает счётчики."""
    now = now or timezone.now()
    stats = {'checked': 0, 'sent': 0, 'no_items': 0, 'no_email': 0, 'failed': 0}
    subs = NotificationSubscription.objects.filter(active=True, user__is_active=True).select_related('user')
    for sub in subs:
        stats['checked'] += 1
        items = items_for(sub, now)
        email = (sub.email or sub.user.email or '').strip()
        if not items or not email:
            stats['no_items' if not items else 'no_email'] += 1
            if not dry_run:
                sub.last_notified_at = now
                sub.save(update_fields=['last_notified_at'])
            continue
        if dry_run:
            stats['sent'] += 1
            continue
        subject, body = build_message(sub, items)
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
        except Exception:
            stats['failed'] += 1
            continue  # время не двигаем: письмо уйдёт при следующем запуске
        sub.last_notified_at = now
        sub.save(update_fields=['last_notified_at'])
        stats['sent'] += 1
    return stats
'''

COMMAND = r'''from django.core.management.base import BaseCommand

from core.mailing import send_financing_digests


class Command(BaseCommand):
    help = ('Рассылка подписчикам о новых грантах и инвестициях. '
            'Запускать по расписанию (например, раз в сутки). --dry-run: только посчитать, ничего не отправлять.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='не отправлять письма и не двигать отметку времени')

    def handle(self, *args, **options):
        s = send_financing_digests(dry_run=options['dry_run'])
        mode = 'Пробный запуск: ' if options['dry_run'] else ''
        self.stdout.write(f"{mode}проверено подписок {s['checked']}, писем {s['sent']}, "
                          f"без новых программ {s['no_items']}, без почты {s['no_email']}, ошибок {s['failed']}")
'''

MIGRATION = r'''import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_currency_tags_service_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationsubscription',
            name='last_notified_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
'''

TESTS = r'''"""Рассылка о грантах и инвестициях."""
from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from . import mailing
from .models import Financing, NotificationSubscription, User


class DigestTests(TestCase):
    def setUp(self):
        mk = User.objects.create_user
        self.u = mk(username='sub', password='pass12345', role='client', email='sub@x.kg')

    def sub(self, **kw):
        data = dict(user=self.u, email='sub@x.kg', financing_updates=True, sector_updates=False, sector='', active=True)
        data.update(kw)
        obj = NotificationSubscription.objects.create(**data)
        # отодвигаем отметку назад, чтобы тесты не зависели от точности часов
        NotificationSubscription.objects.filter(pk=obj.pk).update(last_notified_at=timezone.now() - timedelta(minutes=1))
        obj.refresh_from_db()
        return obj

    def fin(self, title='Грант А', sector='IT'):
        return Financing.objects.create(title=title, financing_type='grant', amount_description='до 1 млн',
                                        description='d', sector=sector)

    def test_sends_new_programs_once(self):
        self.sub()
        self.fin('Грант А')
        s = mailing.send_financing_digests()
        self.assertEqual(s['sent'], 1)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn('Грант А', body)
        self.assertIn('/api/notifications/unsubscribe/?token=', body)
        self.assertEqual(mail.outbox[0].to, ['sub@x.kg'])
        self.assertEqual(mailing.send_financing_digests()['sent'], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_old_programs_not_sent_to_new_subscriber(self):
        f = self.fin('Старый')
        Financing.objects.filter(pk=f.pk).update(created_at=timezone.now() - timedelta(days=3))
        self.sub()
        self.assertEqual(mailing.send_financing_digests()['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sector_filter(self):
        self.sub(financing_updates=False, sector_updates=True, sector='IT')
        self.fin('Про ферму', sector='Сельское хозяйство')
        self.assertEqual(mailing.send_financing_digests()['sent'], 0)
        NotificationSubscription.objects.update(last_notified_at=timezone.now() - timedelta(seconds=5))
        self.fin('Про софт', sector='IT-стартапы')
        self.assertEqual(mailing.send_financing_digests()['sent'], 1)
        self.assertIn('Про софт', mail.outbox[0].body)
        self.assertNotIn('Про ферму', mail.outbox[0].body)

    def test_inactive_and_nothing_selected_get_nothing(self):
        self.sub(active=False)
        self.fin()
        self.assertEqual(mailing.send_financing_digests()['checked'], 0)
        NotificationSubscription.objects.all().delete()
        self.sub(financing_updates=False, sector_updates=False)
        self.fin('Ещё')
        self.assertEqual(mailing.send_financing_digests()['sent'], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_sends_nothing_and_keeps_window(self):
        self.sub()
        self.fin()
        self.assertEqual(mailing.send_financing_digests(dry_run=True)['sent'], 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(mailing.send_financing_digests()['sent'], 1)

    def test_user_email_used_when_subscription_email_empty(self):
        self.sub(email='')
        self.fin()
        mailing.send_financing_digests()
        self.assertEqual(mail.outbox[0].to, ['sub@x.kg'])

    def test_unsubscribe_link(self):
        sub = self.sub()
        api = APIClient()
        r = api.get('/api/notifications/unsubscribe/', {'token': mailing.unsubscribe_token(sub)})
        self.assertEqual(r.status_code, 200)
        sub.refresh_from_db()
        self.assertFalse(sub.active)
        self.assertEqual(api.get('/api/notifications/unsubscribe/', {'token': 'bad'}).status_code, 400)

    def test_reactivation_does_not_send_backlog(self):
        sub = self.sub(active=False)
        NotificationSubscription.objects.filter(pk=sub.pk).update(last_notified_at=timezone.now() - timedelta(days=10))
        self.fin('Пока был выключен')
        api = APIClient()
        api.force_authenticate(self.u)
        r = api.patch(f'/api/notifications/{sub.pk}/', {'active': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(mailing.send_financing_digests()['sent'], 0)
'''

def rd(p): return pathlib.Path(p).read_text(encoding='utf-8')
def wr(p, s):
    pp = pathlib.Path(p); pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(s, encoding='utf-8', newline='\n')
def rep(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit('НЕ УДАЛОСЬ: %s (найдено совпадений: %d). Ничего не изменено.' % (what, n))
    return s.replace(old, new)

if not pathlib.Path('core/models.py').exists():
    sys.exit('Запускайте из корня проекта (там, где manage.py).')
if pathlib.Path('core/mailing.py').exists():
    sys.exit('core/mailing.py уже есть, похоже, патч уже применён. Ничего не делаю.')
mig_dir = pathlib.Path('core/migrations')
if not (mig_dir / '0012_currency_tags_service_logo.py').exists():
    sys.exit('НЕ УДАЛОСЬ: нет миграции 0012_currency_tags_service_logo.py. Пришлите вывод: dir core\\migrations')
if list(mig_dir.glob('0013_*')):
    sys.exit('НЕ УДАЛОСЬ: миграция 0013 уже существует. Пришлите вывод: dir core\\migrations')

m = rd('core/models.py')
m = rep(m, "    sector = models.CharField(max_length=150, blank=True)\n    active = models.BooleanField(default=True)\n",
        "    sector = models.CharField(max_length=150, blank=True)\n    active = models.BooleanField(default=True)\n"
        "    last_notified_at = models.DateTimeField(default=timezone.now)\n", 'поле last_notified_at в модели')

s = rd('core/serializers.py')
s = rep(s, "        model = NotificationSubscription\n        fields = '__all__'\n        read_only_fields = ['user']\n",
        "        model = NotificationSubscription\n        fields = '__all__'\n        read_only_fields = ['user', 'last_notified_at']\n", 'сериализатор подписки')

v = rd('core/views.py')
old_upd = "    def perform_update(self, serializer): serializer.save(email=serializer.validated_data.get('email', self.request.user.email))\n"
new_upd = '''    def perform_update(self, serializer):
        extra = {'email': serializer.validated_data.get('email', self.request.user.email)}
        if serializer.validated_data.get('active') and not serializer.instance.active:
            extra['last_notified_at'] = timezone.now()  # после повторного включения старое не присылаем
        serializer.save(**extra)

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], authentication_classes=[], url_path='unsubscribe')
    def unsubscribe(self, request):
        from . import mailing
        sub = mailing.subscription_from_token(request.query_params.get('token', ''))
        if not sub:
            return HttpResponse('Ссылка недействительна.', status=400, content_type='text/plain; charset=utf-8')
        if sub.active:
            sub.active = False
            sub.save(update_fields=['active'])
        return HttpResponse('Вы отписались от рассылки Connect4Pro. Включить её снова можно в разделе «Аккаунт».',
                            content_type='text/plain; charset=utf-8')
'''
v = rep(v, old_upd, new_upd, 'настройки подписки во views.py')

wr('core/models.py', m); wr('core/serializers.py', s); wr('core/views.py', v)
wr('core/mailing.py', MAILING)
wr('core/management/commands/send_grant_digests.py', COMMAND)
wr('core/migrations/0013_notification_last_notified_at.py', MIGRATION)
wr('core/test_part_e.py', TESTS)
print('Готово. Дальше: python manage.py migrate, затем python manage.py test core.test_part_e')
