"""Платёжный слой: цены, шлюзы (заглушка и Paybox), фиксация оплаты.

Вся бизнес-логика «что даёт оплата» живёт в mark_paid(): шлюзы только создают счёт
и подтверждают факт оплаты, поэтому подмена шлюза не трогает остальной код.
"""
import hashlib
import hmac
import secrets
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .exceptions import PaymentRequired
from .models import PaymentTransaction

DESCRIPTIONS = {
    'premium': 'Подписка Premium Connect4Pro',
    'calculator': 'Калькулятор вероятности получения гранта (разово)',
    'pack_project': 'Пакет из 50 проектов',
    'pack_business_plan': 'Пакет из 50 бизнес-планов',
}
PACK_PURPOSE = {'project': 'pack_project', 'business_plan': 'pack_business_plan'}


class PaymentGatewayError(Exception):
    pass


# ---- Транзакции ------------------------------------------------------------
def create_transaction(user, purpose):
    """Создаёт платёж. Сумма всегда берётся из настроек сервера, а не от клиента."""
    owner = user if (user is not None and user.is_authenticated) else None
    return PaymentTransaction.objects.create(
        user=owner,
        purpose=purpose,
        amount=settings.PRICES_KGS[purpose],
        currency='KGS',
        provider=settings.PAYMENT_GATEWAY,
        description=DESCRIPTIONS[purpose],
        access_token=secrets.token_urlsafe(24),
    )


@transaction.atomic
def mark_paid(tx, external_id=''):
    """Идемпотентно фиксирует оплату и выдаёт купленное. Повторный вызов ничего не удваивает."""
    tx = PaymentTransaction.objects.select_for_update().get(pk=tx.pk)
    if tx.status in ('paid', 'refunded'):
        return tx
    now = timezone.now()
    tx.status = 'paid'
    tx.paid_at = now
    if external_id:
        tx.external_id = external_id
    tx.save(update_fields=['status', 'paid_at', 'external_id'])
    if tx.purpose == 'premium' and tx.user_id:
        _grant_premium(tx.user, now)
    # калькулятор и пакеты ничего не выдают сразу: право считается по оплаченным платежам
    return tx


def _grant_premium(user, now):
    if user.subscription == 'premium' and user.premium_until is None:
        return  # бессрочный Premium (выдан вручную) не ограничиваем
    still_active = user.subscription == 'premium' and user.premium_until and user.premium_until > now
    base = user.premium_until if still_active else now
    user.subscription = 'premium'
    user.premium_until = base + timedelta(days=settings.PREMIUM_PERIOD_DAYS)
    user.save(update_fields=['subscription', 'premium_until'])


def consume_calculator_payment(payment_id, access_token):
    """Списывает одну оплату калькулятора. Атомарно: одна оплата = один расчёт."""
    price = settings.PRICES_KGS['calculator']
    hint = {'price': price, 'currency': 'KGS', 'purpose': 'calculator'}
    try:
        pk = int(payment_id)
    except (TypeError, ValueError):
        raise PaymentRequired('Калькулятор платный: оплатите разовый расчёт или оформите Premium.', **hint)
    if not access_token:
        raise PaymentRequired('Калькулятор платный: оплатите разовый расчёт или оформите Premium.', **hint)
    updated = PaymentTransaction.objects.filter(
        pk=pk, purpose='calculator', status='paid', consumed_at__isnull=True,
        access_token=str(access_token),
    ).update(consumed_at=timezone.now())
    if not updated:
        raise PaymentRequired('Оплата не найдена или уже использована.', **hint)


# ---- Шлюзы -----------------------------------------------------------------
class StubGateway:
    """Заглушка: счёта нет, «оплата» подтверждается вызовом /payments/<id>/stub-pay/."""
    name = 'stub'

    def create_invoice(self, tx, request):
        if not settings.PAYMENTS_STUB_ENABLED:
            raise PaymentGatewayError('Платёжный шлюз не настроен.')
        return {
            'external_id': f'stub-{tx.id}',
            'payment_url': request.build_absolute_uri(f'/api/payments/{tx.id}/stub-pay/'),
        }


def paybox_signature(script_name, params, secret):
    """pg_sig = MD5(имя_скрипта;значения_параметров_по_алфавиту_ключей;секрет)."""
    parts = [script_name] + [str(params[k]) for k in sorted(params)] + [secret]
    return hashlib.md5(';'.join(parts).encode('utf-8')).hexdigest()


class PayboxGateway:
    """Paybox / Freedom Pay. ВАЖНО: написано по описанию протокола, на живом шлюзе не проверялось.
    Когда придут ключи, сверьте имена полей и подпись с документацией Paybox."""
    name = 'paybox'

    def _conf(self):
        if not (settings.PAYBOX_MERCHANT_ID and settings.PAYBOX_SECRET_KEY):
            raise PaymentGatewayError('Не заданы PAYBOX_MERCHANT_ID / PAYBOX_SECRET_KEY.')
        return settings.PAYBOX_MERCHANT_ID, settings.PAYBOX_SECRET_KEY

    def create_invoice(self, tx, request):
        merchant_id, secret = self._conf()
        params = {
            'pg_merchant_id': merchant_id,
            'pg_order_id': str(tx.id),
            'pg_amount': f'{tx.amount:.2f}',
            'pg_currency': tx.currency,
            'pg_description': tx.description,
            'pg_salt': secrets.token_hex(8),
            'pg_result_url': f'{settings.SITE_URL}/api/payments/webhook/paybox/',
            'pg_success_url': f'{settings.SITE_URL}/',
            'pg_failure_url': f'{settings.SITE_URL}/',
        }
        params['pg_sig'] = paybox_signature('init_payment.php', params, secret)
        req = urllib.request.Request(
            f'{settings.PAYBOX_API_URL}/init_payment.php',
            data=urllib.parse.urlencode(params).encode('utf-8'), method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
        except Exception as exc:  # сеть, таймаут, неверный XML
            raise PaymentGatewayError(f'Шлюз Paybox недоступен: {exc}')
        if (root.findtext('pg_status') or '') != 'ok':
            raise PaymentGatewayError(root.findtext('pg_error_description') or 'Paybox отклонил создание счёта.')
        return {
            'external_id': root.findtext('pg_payment_id') or '',
            'payment_url': root.findtext('pg_redirect_url') or '',
        }

    def verify_callback(self, script_name, params):
        _, secret = self._conf()
        given = str(params.get('pg_sig', ''))
        body = {k: v for k, v in params.items() if k != 'pg_sig'}
        return hmac.compare_digest(given.encode('utf-8'), paybox_signature(script_name, body, secret).encode('utf-8'))

    def callback_response(self, script_name, status, description=''):
        """XML-ответ шлюзу на result_url (Paybox ждёт подписанный ответ)."""
        _, secret = self._conf()
        fields = {'pg_status': status, 'pg_description': description, 'pg_salt': secrets.token_hex(8)}
        fields['pg_sig'] = paybox_signature(script_name, fields, secret)
        body = ''.join(f'<{k}>{escape(str(v))}</{k}>' for k, v in fields.items())
        return f'<?xml version="1.0" encoding="utf-8"?><response>{body}</response>'


def get_gateway():
    return PayboxGateway() if settings.PAYMENT_GATEWAY == 'paybox' else StubGateway()
