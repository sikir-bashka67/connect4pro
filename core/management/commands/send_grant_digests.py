from django.core.management.base import BaseCommand

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
