from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _("Зэвсгийн өрөөний удирдлагын систем")
admin.site.site_title = _("Зэвсгийн өрөөний менежмент")
admin.site.index_title = _("Системд тавтай морил")

urlpatterns = [
    path('', RedirectView.as_view(url='dashboard/', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/face/', include('face_authentication.urls')),
    # Add API endpoints if needed for mobile/edge devices
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
