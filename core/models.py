from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = (
        ('client', 'Клиент / МСБ'),
        ('provider', 'Сервис-провайдер'),
        ('admin', 'Администратор'),
    )

    SUBSCRIPTION_CHOICES = (
        ('freemium', 'Freemium'),
        ('premium', 'Premium'),
    )

    TURNOVER_CHOICES = (
        ('up_to_100k', 'до 100 000'),
        ('up_to_500k', 'до 500 000'),
        ('up_to_1m', 'до 1 млн'),
        ('up_to_5m', 'до 5 млн'),
        ('up_to_10m', 'до 10 млн'),
        ('over_10m', 'более 10 млн'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client', verbose_name='Роль')
    subscription = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='freemium', verbose_name='Тип подписки')
    first_name = models.CharField(max_length=150, blank=True, verbose_name='Имя')
    last_name = models.CharField(max_length=150, blank=True, verbose_name='Фамилия')
    birth_year = models.PositiveIntegerField(blank=True, null=True, verbose_name='Год рождения')
    company_name = models.CharField(max_length=255, blank=True, verbose_name='Название компании')
    phone = models.CharField(max_length=30, blank=True, null=True, verbose_name='Телефон / Telegram')
    website_or_social = models.URLField(blank=True, null=True, verbose_name='Сайт или соцсети')
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name='Регион')
    business_sector = models.CharField(max_length=150, blank=True, null=True, verbose_name='Сектор бизнеса')
    employees_count = models.PositiveIntegerField(blank=True, null=True, verbose_name='Число сотрудников')
    annual_turnover = models.CharField(max_length=50, choices=TURNOVER_CHOICES, blank=True, null=True, verbose_name='Примерный оборот за год')
    what_i_offer = models.TextField(blank=True, null=True, verbose_name='Я предлагаю (знания, навыки, технологии)')
    what_i_seek = models.TextField(blank=True, null=True, verbose_name='Я ищу (партнеры, инвесторы, консультации)')

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='core_user_set',
        related_query_name='core_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='core_user_set',
        related_query_name='core_user',
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()} - {self.get_subscription_display()})"


class Category(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name='Название категории')
    slug = models.SlugField(max_length=150, unique=True, verbose_name='Слаг')

    def __str__(self):
        return self.name


class Ad(models.Model):
    title = models.CharField(max_length=255, verbose_name='Заголовок запроса')
    description = models.TextField(verbose_name='Описание запроса')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Бюджет / Цена (сом/доллары)')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='ads', verbose_name='Категория')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ads', verbose_name='Автор (Клиент)')
    what_i_offer_optional = models.TextField(blank=True, null=True, verbose_name='Я предлагаю (опционально)')
    is_completed = models.BooleanField(default=False, verbose_name='Сделка завершена')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    def __str__(self):
        return f"{self.title} ({self.author.username})"


class ProviderService(models.Model):
    provider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='services', limit_choices_to={'role': 'provider'}, verbose_name='Провайдер')
    title = models.CharField(max_length=255, verbose_name='Название услуги')
    description = models.TextField(verbose_name='Описание услуги')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Цена от')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='provider_services', verbose_name='Категория')
    phone = models.CharField(max_length=30, blank=True, null=True, verbose_name='Телефон')
    email = models.EmailField(blank=True, null=True, verbose_name='Почта')
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name='Адрес')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    def __str__(self):
        return f"{self.title} [Провайдер: {self.provider.username}]"


class Financing(models.Model):
    FINANCING_TYPES = (
        ('grant', 'Грант'),
        ('investment', 'Инвестиции'),
    )
    title = models.CharField(max_length=255, verbose_name='Название')
    financing_type = models.CharField(max_length=20, choices=FINANCING_TYPES, verbose_name='Тип финансирования')
    amount_description = models.CharField(max_length=255, verbose_name='Сумма / Условия')
    deadline = models.DateField(blank=True, null=True, verbose_name='Дедлайн')
    description = models.TextField(verbose_name='Полное описание')
    sector = models.CharField(max_length=150, blank=True, null=True, verbose_name='Сектор (например, с/х, IT)')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='financings', verbose_name='Категория')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата публикации')

    def __str__(self):
        return f"[{self.get_financing_type_display()}] {self.title}"


class Event(models.Model):
    EVENT_TYPES = (
        ('training', 'Тренинг / Курс'),
        ('conference', 'Конференция'),
        ('internship', 'Стажировка'),
        ('b2b', 'B2B ивент'),
    )
    title = models.CharField(max_length=255, verbose_name='Название мероприятия')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES, verbose_name='Тип мероприятия')
    date_and_time = models.DateTimeField(verbose_name='Дата и время проведения')
    format = models.CharField(max_length=50, default='Офлайн/Онлайн', verbose_name='Формат')
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name='Место / Ссылка')
    description = models.TextField(verbose_name='Описание')
    sector = models.CharField(max_length=150, blank=True, null=True, verbose_name='Целевой сектор')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='events', verbose_name='Категория')

    def __str__(self):
        return self.title


class DatabaseResource(models.Model):
    RESOURCE_TYPES = (
        ('project', 'Проект'),
        ('business_plan', 'Бизнес-план'),
    )
    resource_type = models.CharField(max_length=30, choices=RESOURCE_TYPES, verbose_name='Тип материала')
    title = models.CharField(max_length=255, verbose_name='Название')
    sector = models.CharField(max_length=150, verbose_name='Сектор / Направление')
    file_or_content = models.TextField(verbose_name='Содержимое / Ссылка на материалы (доступно для Premium)')
    is_premium_only = models.BooleanField(default=True, verbose_name='Только для Premium')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='database_resources', verbose_name='Категория')

    def __str__(self):
        return f"[{self.get_resource_type_display()}] {self.title}"


class Application(models.Model):
    STATUS_CHOICES = (
        ('pending', 'В рассмотрении'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    )
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications', verbose_name='Клиент')
    provider_service = models.ForeignKey(ProviderService, on_delete=models.CASCADE, null=True, blank=True, related_name='applications', verbose_name='Услуга провайдера')
    financing = models.ForeignKey(Financing, on_delete=models.CASCADE, null=True, blank=True, related_name='applications', verbose_name='Грант / Инвестиция')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус заявки')
    message = models.TextField(blank=True, verbose_name='Сопроводительное сообщение')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    def __str__(self):
        return f"Заявка #{self.id} от {self.client.username}"