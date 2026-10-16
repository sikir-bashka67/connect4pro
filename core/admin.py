from django.contrib import admin
from .models import *

for model in [User, ProviderProfile, Category, Ad, AdPhoto, ProviderService, ProviderServicePhoto, Financing, Event, DatabaseResource, Application, ForumTopic, ForumPost, NotificationSubscription, PaymentTransaction, ResourceUnlock, Deal, AnalyticsEvent, Message]:
    admin.site.register(model)
