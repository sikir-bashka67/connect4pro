from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('core', '0006_providerprofile')]
    operations = [
        migrations.AddField(model_name='user', name='premium_until', field=models.DateTimeField(blank=True, null=True, verbose_name='Premium до')),
        migrations.AddField(model_name='user', name='email_updates', field=models.BooleanField(default=True, verbose_name='Получать обновления по email')),
        migrations.AddField(model_name='ad', name='keep_listing', field=models.BooleanField(default=True, verbose_name='Оставить объявление')),
        migrations.AddField(model_name='ad', name='completion_requested_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='ad', name='last_reminder_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='ad', name='auto_bump', field=models.BooleanField(default=False, verbose_name='Автоподнятие объявления')),
        migrations.AddField(model_name='ad', name='last_bumped_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(name='AdPhoto', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('image', models.ImageField(upload_to='ad_photos/')), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('ad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='core.ad')),
        ]),
        migrations.CreateModel(name='ProviderServicePhoto', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('image', models.ImageField(upload_to='service_photos/')), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='core.providerservice')),
        ]),
        migrations.CreateModel(name='ForumTopic', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=255)),
            ('topic_type', models.CharField(choices=[('grants','Гранты / финансирование'),('investments','Инвестиции'),('business_sale','Купля-продажа бизнеса'),('legal','Юридические вопросы'),('general','Общие вопросы')], default='general', max_length=30)),
            ('is_closed', models.BooleanField(default=False)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forum_topics', to='core.user')),
        ]),
        migrations.CreateModel(name='ForumPost', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('text', models.TextField()), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forum_posts', to='core.user')),
            ('topic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='posts', to='core.forumtopic')),
        ]),
        migrations.CreateModel(name='NotificationSubscription', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('email', models.EmailField(blank=True, max_length=254)), ('financing_updates', models.BooleanField(default=True)), ('sector_updates', models.BooleanField(default=True)), ('sector', models.CharField(blank=True, max_length=150)), ('active', models.BooleanField(default=True)),
            ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_subscription', to='core.user')),
        ]),
        migrations.CreateModel(name='PaymentTransaction', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('amount', models.DecimalField(decimal_places=2, max_digits=12)), ('currency', models.CharField(default='KGS', max_length=10)),
            ('status', models.CharField(choices=[('pending','Ожидает оплаты'),('paid','Оплачено'),('failed','Ошибка'),('refunded','Возвращено')], default='pending', max_length=20)),
            ('provider', models.CharField(default='paybox', max_length=50)), ('external_id', models.CharField(blank=True, max_length=255)), ('description', models.CharField(blank=True, max_length=500)), ('created_at', models.DateTimeField(auto_now_add=True)), ('paid_at', models.DateTimeField(blank=True, null=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='core.user')),
        ]),
        migrations.CreateModel(name='Deal', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('status', models.CharField(choices=[('started','Начата'),('completed','Завершена'),('cancelled','Отменена')], default='started', max_length=20)), ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)), ('created_at', models.DateTimeField(auto_now_add=True)), ('completed_at', models.DateTimeField(blank=True, null=True)),
            ('ad', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='deals', to='core.ad')),
            ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='client_deals', to='core.user')),
            ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='provider_deals', to='core.user')),
            ('provider_service', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='deals', to='core.providerservice')),
        ]),
        migrations.CreateModel(name='AnalyticsEvent', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('event_type', models.CharField(choices=[('visit','Посещение'),('click','Клик'),('share','Поделиться'),('traffic','Источник трафика')], max_length=30)),
            ('object_type', models.CharField(blank=True, max_length=50)), ('object_id', models.PositiveIntegerField(blank=True, null=True)), ('source', models.CharField(blank=True, max_length=100)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
        ]),
    ]
