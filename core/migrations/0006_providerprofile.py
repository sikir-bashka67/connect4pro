from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_user_profile_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProviderProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_name', models.CharField(max_length=255, verbose_name='Название компании')),
                ('activity', models.CharField(max_length=255, verbose_name='Сфера деятельности')),
                ('founded_year', models.PositiveIntegerField(blank=True, null=True, verbose_name='Год основания')),
                ('manager_name', models.CharField(max_length=255, verbose_name='ФИО руководителя')),
                ('description', models.TextField(verbose_name='Краткое описание')),
                ('services_description', models.TextField(verbose_name='Список предлагаемых услуг')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='provider_logos/', verbose_name='Логотип')),
                ('phone', models.CharField(blank=True, max_length=30, null=True, verbose_name='Телефон')),
                ('email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='Почта')),
                ('address', models.CharField(blank=True, max_length=255, null=True, verbose_name='Адрес')),
                ('social_link', models.URLField(blank=True, null=True, verbose_name='Соцсети')),
                ('website', models.URLField(blank=True, null=True, verbose_name='Сайт')),
                ('qr_code', models.ImageField(blank=True, null=True, upload_to='provider_qr/', verbose_name='QR-код')),
                ('provider', models.OneToOneField(limit_choices_to={'role': 'provider'}, on_delete=django.db.models.deletion.CASCADE, related_name='provider_profile', to='core.user', verbose_name='Провайдер')),
            ],
        ),
    ]
