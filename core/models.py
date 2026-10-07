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
    premium_until = models.DateTimeField(blank=True, null=True, verbose_name='Premium до')
    email_updates = models.BooleanField(default=True, verbose_name='Получать обновления по email')
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

    def is_premium_active(self):
        from django.utils import timezone
        return self.role == 'admin' or (self.subscription == 'premium' and (self.premium_until is None or self.premium_until > timezone.now()))

    def __str__(self):
        return f"{self.username} ({self.get_role_display()} - {self.get_subscription_display()})"


class ProviderProfile(models.Model):
    provider = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='provider_profile',
        limit_choices_to={'role': 'provider'},
        verbose_name='Провайдер',
    )
    company_name = models.CharField(max_length=255, verbose_name='Название компании')
    activity = models.CharField(max_length=255, verbose_name='Сфера деятельности')
    founded_year = models.PositiveIntegerField(blank=True, null=True, verbose_name='Год основания')
    manager_name = models.CharField(max_length=255, verbose_name='ФИО руководителя')
    description = models.TextField(verbose_name='Краткое описание')
    services_description = models.TextField(verbose_name='Список предлагаемых услуг')
    logo = models.ImageField(upload_to='provider_logos/', blank=True, null=True, verbose_name='Логотип')
    phone = models.CharField(max_length=30, blank=True, null=True, verbose_name='Телефон')
    email = models.EmailField(blank=True, null=True, verbose_name='Почта')
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name='Адрес')
    social_link = models.URLField(blank=True, null=True, verbose_name='Соцсети')
    website = models.URLField(blank=True, null=True, verbose_name='Сайт')
    qr_code = models.ImageField(upload_to='provider_qr/', blank=True, null=True, verbose_name='QR-код')

    def __str__(self):
        return f'{self.company_name} ({self.provider.username})'


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
    keep_listing = models.BooleanField(default=True, verbose_name='Оставить объявление')
    completion_requested_at = models.DateTimeField(blank=True, null=True)
    last_reminder_at = models.DateTimeField(blank=True, null=True)
    auto_bump = models.BooleanField(default=False, verbose_name='Автоподнятие объявления')
    last_bumped_at = models.DateTimeField(blank=True, null=True)
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
        ('case', 'Кейс'),
        ('donor', 'Донор'),
        ('investor', 'Инвестор'),
        ('franchise', 'Франчайзинг'),
        ('sme', 'МСБ'),
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
class AdPhoto(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='ad_photos/')
    created_at = models.DateTimeField(auto_now_add=True)


class ProviderServicePhoto(models.Model):
    service = models.ForeignKey(ProviderService, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='service_photos/')
    created_at = models.DateTimeField(auto_now_add=True)


class ForumTopic(models.Model):
    TOPIC_CHOICES = (
        ('grants', 'Гранты / финансирование'),
        ('investments', 'Инвестиции'),
        ('business_sale', 'Купля-продажа бизнеса'),
        ('legal', 'Юридические вопросы'),
        ('general', 'Общие вопросы'),
    )
    title = models.CharField(max_length=255)
    topic_type = models.CharField(max_length=30, choices=TOPIC_CHOICES, default='general')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_topics')
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ForumPost(models.Model):
    topic = models.ForeignKey(ForumTopic, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_posts')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationSubscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_subscription')
    email = models.EmailField(blank=True)
    financing_updates = models.BooleanField(default=True)
    sector_updates = models.BooleanField(default=True)
    sector = models.CharField(max_length=150, blank=True)
    active = models.BooleanField(default=True)


class PaymentTransaction(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Ожидает оплаты'),
        ('paid', 'Оплачено'),
        ('failed', 'Ошибка'),
        ('refunded', 'Возвращено'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='KGS')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    provider = models.CharField(max_length=50, default='paybox')
    external_id = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)


class Deal(models.Model):
    STATUS_CHOICES = (
        ('started', 'Начата'),
        ('completed', 'Завершена'),
        ('cancelled', 'Отменена'),
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, null=True, blank=True, related_name='deals')
    provider_service = models.ForeignKey(ProviderService, on_delete=models.CASCADE, null=True, blank=True, related_name='deals')
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_deals')
    provider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='provider_deals')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)


class AnalyticsEvent(models.Model):
    EVENT_CHOICES = (
        ('visit', 'Посещение'),
        ('click', 'Клик'),
        ('share', 'Поделиться'),
        ('traffic', 'Источник трафика'),
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
