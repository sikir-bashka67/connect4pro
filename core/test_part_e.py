"""Рассылка о грантах и инвестициях."""
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
