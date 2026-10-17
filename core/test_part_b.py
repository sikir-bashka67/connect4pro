"""Блок B: кабинет провайдера (профиль, услуги, фото) и CRM (заявки, сделки)."""
import io
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework import serializers
from rest_framework.test import APIClient

from .models import Ad, Application, Deal, ProviderProfile, ProviderService, User
from .serializers import validate_image_size

TMP_MEDIA = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(TMP_MEDIA, ignore_errors=True)


def png(name='a.png'):
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buf, 'PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


PROFILE = {'company_name': 'Acme', 'activity': 'Консалтинг', 'manager_name': 'Иван Иванов',
           'description': 'Помогаем', 'services_description': 'Бизнес-планы'}


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class PartBBase(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        mk = User.objects.create_user
        self.provider = mk(username='prov', password='pass12345', role='provider', email='p@x.kg')
        self.provider2 = mk(username='prov2', password='pass12345', role='provider', email='p2@x.kg')
        self.client_u = mk(username='cl', password='pass12345', role='client', email='c@x.kg', company_name='ООО Ромашка')
        self.service = ProviderService.objects.create(provider=self.provider, title='Бизнес-план',
                                                      description='d', price='10000')

    def as_user(self, user):
        self.api.force_authenticate(user)
        return self.api


class ImageSizeTests(SimpleTestCase):
    def test_size_limit(self):
        class F:  # минимальная подмена файла
            def __init__(self, size):
                self.size = size
        self.assertIsNotNone(validate_image_size(F(5 * 1024 * 1024)))
        with self.assertRaises(serializers.ValidationError):
            validate_image_size(F(5 * 1024 * 1024 + 1))
        self.assertIsNone(validate_image_size(None))


class ProviderCabinetTests(PartBBase):
    def test_profile_create_with_logo_and_lookup_by_provider(self):
        r = self.as_user(self.provider).post('/api/provider-profiles/', {**PROFILE, 'phone': '+996555', 'logo': png()}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        r = self.api.get(f'/api/provider-profiles/?provider={self.provider.id}')
        self.assertEqual(len(r.data['results']), 1)
        self.assertEqual(r.data['results'][0]['phone'], '+996555')      # владелец видит свои контакты
        self.assertTrue(r.data['results'][0]['logo'])
        self.assertEqual(self.api.post('/api/provider-profiles/', PROFILE, format='multipart').status_code, 400)  # второй профиль

    def test_profile_year_validation_and_foreign_edit(self):
        self.as_user(self.provider).post('/api/provider-profiles/', PROFILE, format='multipart')
        pid = ProviderProfile.objects.get(provider=self.provider).id
        self.assertEqual(self.api.patch(f'/api/provider-profiles/{pid}/', {'founded_year': 1500}, format='multipart').status_code, 400)
        self.assertEqual(self.api.patch(f'/api/provider-profiles/{pid}/', {'founded_year': 2015}, format='multipart').status_code, 200)
        self.as_user(self.provider2)
        self.assertEqual(self.api.patch(f'/api/provider-profiles/{pid}/', {'activity': 'взлом'}, format='multipart').status_code, 403)

    def test_service_with_logo_currency_tags_and_photo_limit(self):
        r = self.as_user(self.provider).post('/api/provider-services/', {
            'title': 'Сайт-визитка', 'description': 'd', 'price': '5000', 'currency': 'USD',
            'tags': ' IT,it', 'logo': png()}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['currency'], r.data['tags']), ('USD', 'it'))
        sid = r.data['id']
        for _ in range(5):
            self.assertEqual(self.api.post('/api/service-photos/', {'service': sid, 'image': png()}, format='multipart').status_code, 201)
        self.assertEqual(self.api.post('/api/service-photos/', {'service': sid, 'image': png()}, format='multipart').status_code, 400)

    def test_foreign_provider_cannot_upload_photo_to_my_service(self):
        r = self.as_user(self.provider2).post('/api/service-photos/', {'service': self.service.id, 'image': png()}, format='multipart')
        self.assertEqual(r.status_code, 403)


class ApplicationCrmTests(PartBBase):
    def apply(self):
        r = self.as_user(self.client_u).post('/api/applications/', {'provider_service': self.service.id, 'message': 'Нужен БП'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_provider_sees_only_own_applications_with_names(self):
        self.apply()
        r = self.as_user(self.provider).get('/api/applications/')
        self.assertEqual(len(r.data['results']), 1)
        row = r.data['results'][0]
        self.assertEqual((row['client_name'], row['service_title']), ('ООО Ромашка', 'Бизнес-план'))
        self.assertEqual(len(self.as_user(self.provider2).get('/api/applications/').data['results']), 0)

    def test_only_provider_changes_status(self):
        app = self.apply()
        self.assertEqual(self.as_user(self.client_u).patch(f'/api/applications/{app["id"]}/', {'status': 'approved'}, format='json').status_code, 403)
        r = self.as_user(self.provider).patch(f'/api/applications/{app["id"]}/', {'status': 'approved'}, format='json')
        self.assertEqual((r.status_code, r.data['status']), (200, 'approved'))

    def test_create_deal_from_application_is_idempotent(self):
        app = self.apply()
        r = self.as_user(self.provider).post(f'/api/applications/{app["id"]}/create-deal/', {}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['client'], r.data['provider'], r.data['title']), (self.client_u.id, self.provider.id, 'Бизнес-план'))
        self.assertEqual(Application.objects.get(id=app['id']).status, 'approved')
        r2 = self.api.post(f'/api/applications/{app["id"]}/create-deal/', {}, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(Deal.objects.count(), 1)

    def test_rejected_application_cannot_become_deal_and_strangers_get_404(self):
        app = self.apply()
        self.assertEqual(self.as_user(self.provider2).post(f'/api/applications/{app["id"]}/create-deal/').status_code, 404)
        self.as_user(self.provider).patch(f'/api/applications/{app["id"]}/', {'status': 'rejected'}, format='json')
        self.assertEqual(self.api.post(f'/api/applications/{app["id"]}/create-deal/').status_code, 400)

    def test_client_can_withdraw_own_application(self):
        app = self.apply()
        self.assertEqual(self.as_user(self.client_u).delete(f'/api/applications/{app["id"]}/').status_code, 204)


class DealLifecycleTests(PartBBase):
    def open_deal(self):
        r = self.as_user(self.client_u).post('/api/deals/', {'provider_service': self.service.id, 'amount': '999999'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_client_cannot_set_amount_on_create_or_later(self):
        d = self.open_deal()
        self.assertEqual(Deal.objects.get(id=d['id']).amount, 0)
        self.assertEqual(self.api.post(f'/api/deals/{d["id"]}/amount/', {'amount': '5'}, format='json').status_code, 403)

    def test_duplicate_open_deal_and_wrong_role(self):
        self.open_deal()
        self.assertEqual(self.api.post('/api/deals/', {'provider_service': self.service.id}, format='json').status_code, 400)
        r = self.as_user(self.provider2).post('/api/deals/', {'provider_service': self.service.id}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_provider_sets_amount_then_completes_once(self):
        d = self.open_deal()
        self.as_user(self.provider)
        self.assertEqual(self.api.post(f'/api/deals/{d["id"]}/amount/', {'amount': 'abc'}, format='json').status_code, 400)
        r = self.api.post(f'/api/deals/{d["id"]}/amount/', {'amount': '12500.50'}, format='json')
        self.assertEqual((r.status_code, r.data['amount']), (200, '12500.50'))
        r = self.api.post(f'/api/deals/{d["id"]}/complete/')
        self.assertEqual((r.status_code, r.data['status']), (200, 'completed'))
        self.assertEqual(self.api.post(f'/api/deals/{d["id"]}/complete/').status_code, 400)
        self.assertEqual(self.api.post(f'/api/deals/{d["id"]}/cancel/').status_code, 400)
        self.assertEqual(self.api.post(f'/api/deals/{d["id"]}/amount/', {'amount': '1'}, format='json').status_code, 400)

    def test_cancel_and_no_direct_edit_or_delete(self):
        d = self.open_deal()
        self.assertEqual(self.api.patch(f'/api/deals/{d["id"]}/', {'amount': '1'}, format='json').status_code, 405)
        self.assertEqual(self.api.delete(f'/api/deals/{d["id"]}/').status_code, 405)
        r = self.api.post(f'/api/deals/{d["id"]}/cancel/')
        self.assertEqual((r.status_code, r.data['status']), (200, 'cancelled'))

    def test_stranger_does_not_see_deal(self):
        d = self.open_deal()
        self.assertEqual(self.as_user(self.provider2).get(f'/api/deals/{d["id"]}/').status_code, 404)

    def test_provider_deal_on_client_ad_completes_the_ad(self):
        ad = Ad.objects.create(author=self.client_u, title='Нужен сайт', description='d', price='8000')
        r = self.as_user(self.provider).post('/api/deals/', {'ad': ad.id}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['client'], self.client_u.id)
        self.api.post(f'/api/deals/{r.data["id"]}/complete/')
        ad.refresh_from_db()
        self.assertTrue(ad.is_completed)
