from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Ad


class Command(BaseCommand):
    help = ('Плановые задачи: автоподнятие объявлений Premium, напоминания по объявлениям, '
            'удаление завершённых объявлений через 3 дня. Запускать по расписанию (например, раз в час).')

    def handle(self, *args, **options):
        now = timezone.now()
        reminders = deleted = bumped = 0

        # 1. Автоподнятие: только для авторов с действующим Premium, не чаще заданного интервала
        interval = timedelta(hours=settings.AUTO_BUMP_INTERVAL_HOURS)
        for ad in Ad.objects.filter(auto_bump=True, is_completed=False).select_related('author'):
            if not ad.author.is_premium_active():
                continue
            last = ad.last_bumped_at or ad.created_at
            if last <= now - interval:
                ad.last_bumped_at = now
                ad.save(update_fields=['last_bumped_at'])
                bumped += 1

        # 2. Удаление завершённых сделок через 3 дня
        for ad in Ad.objects.filter(is_completed=True):
            if ad.completion_requested_at and ad.completion_requested_at <= now - timedelta(days=3):
                ad.delete()
                deleted += 1

        # 3. Напоминания раз в 2 недели по незавершённым объявлениям
        for ad in Ad.objects.filter(is_completed=False, keep_listing=True):
            if ad.last_reminder_at is None or ad.last_reminder_at <= now - timedelta(days=14):
                if ad.author.email:
                    send_mail('Connect4Pro: напоминание об объявлении',
                              f'Проверьте актуальность объявления: {ad.title}', None, [ad.author.email])
                ad.last_reminder_at = now
                ad.save(update_fields=['last_reminder_at'])
                reminders += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово: поднято {bumped}, напоминаний {reminders}, удалено объявлений {deleted}.'))
