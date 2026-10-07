from rest_framework import serializers
from .models import (
    User, ProviderProfile, Category, Ad, AdPhoto, ProviderService, ProviderServicePhoto,
    Financing, Event, DatabaseResource, Application, ForumTopic, ForumPost,
    NotificationSubscription, PaymentTransaction, Deal, AnalyticsEvent,
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=['client', 'provider'], default='client', write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name', 'birth_year',
                  'company_name', 'phone', 'website_or_social', 'region', 'business_sector',
                  'employees_count', 'annual_turnover', 'what_i_offer', 'what_i_seek', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role', 'client')
        return User.objects.create_user(**validated_data, role=role, subscription='freemium')


class UserSerializer(serializers.ModelSerializer):
    is_premium = serializers.SerializerMethodField()
    class Meta:
        model = User
        exclude = ['password', 'groups', 'user_permissions', 'is_superuser']
        read_only_fields = ['role', 'subscription', 'premium_until', 'is_staff', 'is_active', 'last_login', 'date_joined']
    def get_is_premium(self, obj):
        return obj.is_premium_active()


class ProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = '__all__'
        extra_kwargs = {'provider': {'required': False}}


class PublicProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = ['id', 'company_name', 'activity', 'founded_year', 'description', 'services_description', 'logo', 'website']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class AdPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdPhoto
        fields = '__all__'
        read_only_fields = ['created_at']


class AdSerializer(serializers.ModelSerializer):
    photos = AdPhotoSerializer(many=True, read_only=True)
    class Meta:
        model = Ad
        fields = '__all__'
        read_only_fields = ['author', 'created_at', 'completion_requested_at', 'last_reminder_at', 'last_bumped_at']


class ProviderServicePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderServicePhoto
        fields = '__all__'
        read_only_fields = ['created_at']


class ProviderServiceSerializer(serializers.ModelSerializer):
    photos = ProviderServicePhotoSerializer(many=True, read_only=True)
    class Meta:
        model = ProviderService
        fields = '__all__'
        read_only_fields = ['provider', 'created_at']


class FinancingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Financing
        fields = '__all__'


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = '__all__'


class DatabaseResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseResource
        fields = '__all__'


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ['client', 'status', 'created_at']
    def validate(self, attrs):
        if bool(attrs.get('provider_service')) == bool(attrs.get('financing')):
            raise serializers.ValidationError('Нужно указать либо услугу провайдера, либо грант/инвестицию.')
        return attrs


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


class NotificationSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSubscription
        fields = '__all__'
        read_only_fields = ['user']


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = '__all__'
        read_only_fields = ['user', 'status', 'external_id', 'paid_at', 'created_at']


class DealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deal
        fields = '__all__'
        read_only_fields = ['client', 'provider', 'created_at', 'completed_at']
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
