from django.contrib import admin
from .models import User, Category, Ad, ProviderService, Financing, Event, DatabaseResource


admin.site.register(User)
admin.site.register(Category)
admin.site.register(Ad)
admin.site.register(ProviderService)
admin.site.register(Financing)
admin.site.register(Event)
admin.site.register(DatabaseResource)