from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User


class OrgLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['password'].widget.attrs['class'] = 'form-control'
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'


class OrgAccountCreateForm(forms.Form):
    username = forms.CharField(max_length=150, label='Логин')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['class'] = 'form-control'

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username
