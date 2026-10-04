from rest_framework import serializers
from .models import User, Category, Ad, ProviderService, Financing, Event, DatabaseResource, Application


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'username', 'password', 'email', 'first_name', 'last_name', 'birth_year',
            'company_name', 'phone', 'website_or_social', 'region', 'business_sector',
            'employees_count', 'annual_turnover', 'what_i_offer', 'what_i_seek'
        ]

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            birth_year=validated_data.get('birth_year'),
            company_name=validated_data.get('company_name', ''),
            phone=validated_data.get('phone', ''),
            website_or_social=validated_data.get('website_or_social', ''),
            region=validated_data.get('region', ''),
            business_sector=validated_data.get('business_sector', ''),
            employees_count=validated_data.get('employees_count'),
            annual_turnover=validated_data.get('annual_turnover'),
            what_i_offer=validated_data.get('what_i_offer', ''),
            what_i_seek=validated_data.get('what_i_seek', ''),
            role='client',
            subscription='freemium',
        )


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class AdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ad
        fields = '__all__'
        read_only_fields = ['author', 'created_at']


class ProviderServiceSerializer(serializers.ModelSerializer):
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
        provider_service = attrs.get('provider_service')
        financing = attrs.get('financing')
        if bool(provider_service) == bool(financing):
            raise serializers.ValidationError('Нужно указать либо услугу провайдера, либо грант/инвестицию.')
        return attrs
