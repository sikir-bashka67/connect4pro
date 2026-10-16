from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from .models import (
    User, ProviderProfile, Category, Ad, AdPhoto, ProviderService, ProviderServicePhoto,
    Financing, Event, DatabaseResource, Application, ForumTopic, ForumPost,
    NotificationSubscription, PaymentTransaction, Deal, AnalyticsEvent,
)
from . import services

OFFER_WARNING = (
    'Информация в поле «Я предлагаю» будет видна остальным клиентам и консультантам. '
    'Подтвердите согласие (consent_public_offer=true).'
)


def viewer_is_premium(request):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and user.is_premium_active())


def viewer_is(request, owner):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and (user == owner or user.role == 'admin'))


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(choices=['client', 'provider'], default='client', write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name', 'birth_year',
                  'company_name', 'phone', 'website_or_social', 'region', 'business_sector',
                  'employees_count', 'annual_turnover', 'what_i_offer', 'what_i_seek',
                  'consent_public_offer', 'role']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Пользователь с такой почтой уже зарегистрирован.')
        return value.lower()

    def validate_birth_year(self, value):
        if value is not None and not (1900 <= value <= timezone.now().year - 14):
            raise serializers.ValidationError('Укажите корректный год рождения.')
        return value

    def validate(self, attrs):
        validate_password(attrs['password'], User(username=attrs.get('username', ''), email=attrs.get('email', '')))
        if attrs.get('what_i_offer') and not attrs.get('consent_public_offer'):
            raise serializers.ValidationError({'consent_public_offer': OFFER_WARNING})
        return attrs

    def create(self, validated_data):
        role = validated_data.pop('role', 'client')
        return User.objects.create_user(**validated_data, role=role, subscription='freemium')


class UserSerializer(serializers.ModelSerializer):
    """Own profile (/me/). Never exposed to other users."""
    is_premium = serializers.SerializerMethodField()

    class Meta:
        model = User
        exclude = ['password', 'groups', 'user_permissions', 'is_superuser']
        read_only_fields = ['username', 'role', 'subscription', 'premium_until', 'is_staff', 'is_active',
                            'last_login', 'date_joined']

    def get_is_premium(self, obj):
        return obj.is_premium_active()

    def validate(self, attrs):
        offer = attrs.get('what_i_offer', self.instance.what_i_offer if self.instance else None)
        consent = attrs.get('consent_public_offer', self.instance.consent_public_offer if self.instance else False)
        if offer and not consent:
            raise serializers.ValidationError({'consent_public_offer': OFFER_WARNING})
        return attrs


# ---- Клиенты (раздел «База данных МСБ») -----------------------------------
GUEST_FIELDS = ['what_i_offer']
REGISTERED_FIELDS = ['business_sector', 'what_i_offer']
PREMIUM_FIELDS = ['first_name', 'last_name', 'company_name', 'email', 'phone', 'website_or_social',
                  'region', 'business_sector', 'employees_count', 'what_i_offer', 'what_i_seek']


class ClientDirectorySerializer(serializers.ModelSerializer):
    """Visibility by ТЗ: guest — only knowledge/skills; registered — + sector;
    premium — name, contacts, sector, employees, knowledge/skills (+ what the client seeks)."""

    class Meta:
        model = User
        fields = ['id'] + PREMIUM_FIELDS

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if viewer_is_premium(request):
            allowed = PREMIUM_FIELDS
        elif user and user.is_authenticated:
            allowed = REGISTERED_FIELDS
        else:
            allowed = GUEST_FIELDS
        return {k: v for k, v in data.items() if k == 'id' or k in allowed}


# ---- Провайдеры ----------------------------------------------------------
PROVIDER_PUBLIC = ['id', 'company_name', 'activity', 'founded_year', 'description',
                   'services_description', 'logo']
PROVIDER_PRIVATE = ['manager_name', 'phone', 'email', 'address', 'social_link', 'website', 'qr_code']


class ProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = '__all__'
        extra_kwargs = {'provider': {'required': False}}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not (viewer_is_premium(request) or viewer_is(request, instance.provider)):
            for f in PROVIDER_PRIVATE:
                data.pop(f, None)
        return data


class PublicProviderProfileSerializer(ProviderProfileSerializer):
    pass


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class AdPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdPhoto
        fields = '__all__'
        read_only_fields = ['created_at']

    def validate_ad(self, ad):
        if self.instance and ad != self.instance.ad:
            raise serializers.ValidationError('Нельзя переносить фото в другое объявление.')
        return ad


class AdSerializer(serializers.ModelSerializer):
    photos = AdPhotoSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Ad
        fields = '__all__'
        read_only_fields = ['author', 'created_at', 'completion_requested_at', 'last_reminder_at',
                            'last_bumped_at', 'is_completed', 'keep_listing', 'auto_bump']

    def get_author_name(self, obj):
        return obj.author.company_name or obj.author.first_name or obj.author.username


class ProviderServicePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderServicePhoto
        fields = '__all__'
        read_only_fields = ['created_at']

    def validate_service(self, service):
        if self.instance and service != self.instance.service:
            raise serializers.ValidationError('Нельзя переносить фото в другую услугу.')
        return service


class ProviderServiceSerializer(serializers.ModelSerializer):
    photos = ProviderServicePhotoSerializer(many=True, read_only=True)

    class Meta:
        model = ProviderService
        fields = '__all__'
        read_only_fields = ['provider', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not (viewer_is_premium(request) or viewer_is(request, instance.provider)):
            for f in ('phone', 'email', 'address'):
                data.pop(f, None)
        return data


class FinancingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Financing
        fields = '__all__'


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = '__all__'


class DatabaseResourceSerializer(serializers.ModelSerializer):
    """Содержимое (file_or_content) показывается только тем, у кого есть доступ:
    админ, свободные материалы, открытые проекты/бизнес-планы, Premium для остальных типов."""
    content_available = serializers.SerializerMethodField()

    class Meta:
        model = DatabaseResource
        fields = '__all__'

    def _viewer(self):
        return getattr(self.context.get('request'), 'user', None)

    def get_content_available(self, obj):
        return services.can_read_content(self._viewer(), obj, self.context.get('unlocks'))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data['content_available']:
            data.pop('file_or_content', None)
        return data


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ['client', 'status', 'created_at']

    def validate(self, attrs):
        if self.instance is None and bool(attrs.get('provider_service')) == bool(attrs.get('financing')):
            raise serializers.ValidationError('Нужно указать либо услугу провайдера, либо грант/инвестицию.')
        return attrs


class ApplicationReviewSerializer(serializers.ModelSerializer):
    """Used by provider/admin: only the status may be changed."""

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ['client', 'provider_service', 'financing', 'message', 'created_at']


class ForumTopicSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = ForumTopic
        fields = '__all__'
        read_only_fields = ['author', 'created_at', 'updated_at']


class ForumPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = ForumPost
        fields = '__all__'
        read_only_fields = ['author', 'created_at']

    def validate_topic(self, topic):
        if self.instance and topic != self.instance.topic:
            raise serializers.ValidationError('Нельзя переносить сообщение в другую тему.')
        return topic


class NotificationSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSubscription
        fields = '__all__'
        read_only_fields = ['user']


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Только для чтения: платежи создаются через /payments/checkout/, сумма задаётся сервером.
    access_token здесь намеренно нет: он выдаётся один раз при создании платежа."""

    class Meta:
        model = PaymentTransaction
        fields = ['id', 'user', 'purpose', 'amount', 'currency', 'status', 'provider',
                  'external_id', 'payment_url', 'description', 'consumed_at', 'created_at', 'paid_at']
        read_only_fields = fields


class DealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deal
        fields = '__all__'
        read_only_fields = ['client', 'provider', 'created_at', 'completed_at', 'status']

    def validate(self, attrs):
        if not attrs.get('ad') and not attrs.get('provider_service'):
            raise serializers.ValidationError('Укажите объявление или услугу провайдера.')
        if attrs.get('ad') and attrs.get('provider_service'):
            raise serializers.ValidationError('Нельзя одновременно указывать объявление и услугу.')
        return attrs


class AnalyticsEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsEvent
        fields = '__all__'
        read_only_fields = ['user', 'created_at']
