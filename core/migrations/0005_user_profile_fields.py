from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_databaseresource_category_event_category_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='first_name',
            field=models.CharField(blank=True, max_length=150, verbose_name='Имя'),
        ),
        migrations.AddField(
            model_name='user',
            name='last_name',
            field=models.CharField(blank=True, max_length=150, verbose_name='Фамилия'),
        ),
        migrations.AddField(
            model_name='user',
            name='birth_year',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Год рождения'),
        ),
        migrations.AddField(
            model_name='user',
            name='company_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Название компании'),
        ),
    ]
