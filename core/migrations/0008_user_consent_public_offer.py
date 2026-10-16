from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_platform_features'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='consent_public_offer',
            field=models.BooleanField(
                default=False,
                verbose_name='Согласен, что «Я предлагаю» будет видно другим клиентам и консультантам',
            ),
        ),
    ]
