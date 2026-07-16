from django.contrib import admin

from .models import Analysis, DetectedItem, StyleScore

admin.site.register(Analysis)
admin.site.register(DetectedItem)
admin.site.register(StyleScore)
