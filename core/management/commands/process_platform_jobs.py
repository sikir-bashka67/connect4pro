from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from core.models import Ad, NotificationSubscription

class Command(BaseCommand):
    help = 'Обрабатывает напоминания по объявлениям и удаляет завершенные объявления через 3 дня.'
    def handle(self, *args, **options):
        now = timezone.now()
        reminders = 0
        deleted = 0
        for ad in Ad.objects.filter(is_completed=True):
            if ad.completion_requested_at and ad.completion_requested_at <= now - timezone.timedelta(days=3):
                ad.delete(); deleted += 1
                continue
        for ad in Ad.objects.filter(is_completed=False, keep_listing=True):
            if ad.last_reminder_at is None or ad.last_reminder_at <= now - timezone.timedelta(days=14):
                if ad.author.email:
                    send_mail('Connect4Pro: напоминание об объявлении', f'Проверьте актуальность объявления: {ad.title}', None, [ad.author.email])
                ad.last_reminder_at = now
                ad.save(update_fields=['last_reminder_at'])
                reminders += 1
        self.stdout.write(self.style.SUCCESS(f'Готово: напоминаний {reminders}, удалено объявлений {deleted}.'))
