"""Лимиты баз данных Premium: 10 проектов + 10 бизнес-планов в подписке, докупка пакетами по 50."""
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .exceptions import PaymentRequired
from .models import PaymentTransaction, ResourceUnlock, User
from .payments import PACK_PURPOSE

QUOTA_TYPES = tuple(PACK_PURPOSE)  # ('project', 'business_plan')


def quota_status(user, resource_type):
    """Сколько материалов этого типа пользователь уже открыл и сколько ещё может."""
    unlocks = ResourceUnlock.objects.filter(user=user, resource__resource_type=resource_type)
    included_used = unlocks.filter(source='subscription').count()
    pack_used = unlocks.filter(source='pack').count()
    packs_paid = PaymentTransaction.objects.filter(
        user=user, purpose=PACK_PURPOSE[resource_type], status='paid').count()
    pack_total = packs_paid * settings.RESOURCE_PACK_SIZE
    included_limit = settings.PREMIUM_INCLUDED_RESOURCES
    included_left = max(0, included_limit - included_used) if user.is_premium_active() else 0
    return {
        'included_limit': included_limit,
        'included_used': included_used,
        'included_left': included_left,
        'pack_total': pack_total,
        'pack_used': pack_used,
        'pack_left': max(0, pack_total - pack_used),
        'pack_size': settings.RESOURCE_PACK_SIZE,
        'pack_purpose': PACK_PURPOSE[resource_type],
    }


def unlock_resource(user, resource):
    """Открывает материал. Повторное открытие бесплатно. Сначала тратятся места подписки, потом пакета."""
    if resource.resource_type not in QUOTA_TYPES:
        raise PermissionDenied('Для этого типа материалов лимиты не применяются.')
    if not user.is_premium_active():
        raise PermissionDenied('Открывать проекты и бизнес-планы могут подписчики Premium.')
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)  # сериализуем параллельные открытия
        existing = ResourceUnlock.objects.filter(user=user, resource=resource).first()
        if existing:
            return existing
        q = quota_status(user, resource.resource_type)
        if q['included_left'] > 0:
            source = 'subscription'
        elif q['pack_left'] > 0:
            source = 'pack'
        else:
            raise PaymentRequired(
                f'Лимит исчерпан: {q["included_limit"]} в подписке уже открыты. '
                f'Докупите пакет из {q["pack_size"]}.',
                purchase=q['pack_purpose'], pack_size=q['pack_size'],
                price=settings.PRICES_KGS[q['pack_purpose']], currency='KGS')
        return ResourceUnlock.objects.create(user=user, resource=resource, source=source)


def unlock_map(user):
    """{resource_id: source} для списка; один запрос на весь список."""
    if user is None or not user.is_authenticated:
        return {}
    return dict(ResourceUnlock.objects.filter(user=user).values_list('resource_id', 'source'))


def can_read_content(user, resource, unlocks=None):
    """Видит ли зритель содержимое (file_or_content) материала."""
    if user is not None and user.is_authenticated and user.role == 'admin':
        return True
    if not resource.is_premium_only:
        return True
    if user is None or not user.is_authenticated:
        return False
    if resource.resource_type in QUOTA_TYPES:
        if unlocks is None:
            unlocks = unlock_map(user)
        source = unlocks.get(resource.id)
        # купленное в пакете остаётся доступным и после окончания подписки
        return source == 'pack' or (source == 'subscription' and user.is_premium_active())
    return user.is_premium_active()


# Подсказки «Рекомендуемая цена на услуги» из ТЗ (показываются в форме объявления)
PRICE_HINTS = [
    {'title': 'Написание деловой рекомендации', 'price': '200–500 сом'},
    {'title': 'Разработка презентации', 'price': '500–5 000 сом'},
    {'title': 'Заполнение заявки на конкурс', 'price': 'от 1 000 сом'},
    {'title': 'Помощь в подготовке пакета документов на конкурс', 'price': 'от 2 000 сом'},
    {'title': 'Разработка небольшого проекта', 'price': 'от 10 000 сом и более'},
    {'title': 'Разработка небольшого бизнес-плана', 'price': 'от 10 000 сом'},
    {'title': 'Разработка сайта-визитки', 'price': 'от 5 000 сом'},
    {'title': 'Разработка веб-сайта', 'price': 'от 8 000 сом'},
    {'title': 'Получение консультации по конкурсу', 'price': 'от 1 000 сом'},
    {'title': 'Тренинг / семинар на бизнес-тему', 'price': 'от 5 000 сом'},
    {'title': 'Перевод документов на английский и наоборот', 'price': 'от 500 сом за страницу'},
    {'title': 'Помощь с поисками партнёров', 'price': 'договорная'},
    {'title': 'Бизнес-консультации начинающих консультантов', 'price': 'от 50 $ в день'},
    {'title': 'Бизнес-консультации опытных консультантов', 'price': 'от 150 $ в день'},
]
