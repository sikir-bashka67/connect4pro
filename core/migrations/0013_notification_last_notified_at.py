import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_currency_tags_service_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationsubscription',
            name='last_notified_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
