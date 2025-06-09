from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from authentication import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

def home(request):
    return render(request, 'index.html')

def editor(request):
    return render(request, 'editor.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),

    path('', home, name='index'),
    path('library/', views.library_view, name='library'),
    path('editor/', editor, name='editor'),
    path('converter/', views.converter, name='converter'),
    path('search/', views.search_sounds, name='search_sounds'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.custom_logout, name='logout'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
