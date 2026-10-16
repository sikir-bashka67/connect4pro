from django.db import migrations, models

CURRENCIES = [('KGS', 'Сом'), ('USD', 'Доллар')]


def tags_field():
    return models.CharField(blank=True, default='', max_length=255, verbose_name='Теги (через запятую)')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_message'),
    ]

    operations = [
        migrations.AddField(model_name='ad', name='currency',
                            field=models.CharField(choices=CURRENCIES, default='KGS', max_length=3, verbose_name='Валюта')),
        migrations.AddField(model_name='ad', name='tags', field=tags_field()),
        migrations.AddField(model_name='providerservice', name='currency',
                            field=models.CharField(choices=CURRENCIES, default='KGS', max_length=3, verbose_name='Валюта')),
        migrations.AddField(model_name='providerservice', name='logo',
                            field=models.ImageField(blank=True, null=True, upload_to='service_logos/', verbose_name='Логотип')),
        migrations.AddField(model_name='providerservice', name='tags', field=tags_field()),
        migrations.AddField(model_name='financing', name='tags', field=tags_field()),
        migrations.AddField(model_name='event', name='tags', field=tags_field()),
    ]
