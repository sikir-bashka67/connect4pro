"""Рассылка о новых программах финансирования (гранты и инвестиции)."""
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
