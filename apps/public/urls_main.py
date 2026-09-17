from django.urls import path
from django.shortcuts import redirect
from apps.readers import views as reader_views

app_name = 'main'


def home(request):
    return redirect('/catalog/')


urlpatterns = [
    path('', home, name='home'),
    path('login/', reader_views.login_view, name='login'),
    path('logout/', reader_views.logout_view, name='logout'),
    path('my/', reader_views.my_cabinet, name='my'),
    path('my/request/<int:pk>/cancel/', reader_views.my_request_cancel, name='cancel_request'),
    path('my/take/', reader_views.take_book, name='take_book'),
    path('my/return/<int:pk>/', reader_views.return_loan, name='return_loan'),
    path('my/profile/', reader_views.edit_profile, name='edit_profile'),
]
