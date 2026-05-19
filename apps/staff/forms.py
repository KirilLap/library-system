from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from .models import StaffProfile


class _PasswordMixin(forms.Form):
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    password2 = forms.CharField(
        label='Повторите пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean(self):
        cd = super().clean()
        p1 = cd.get('password1')
        p2 = cd.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Пароли не совпадают.')
        return cd


class StaffInitForm(_PasswordMixin):
    first_name = forms.CharField(
        label='Имя', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label='Фамилия', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    username = forms.CharField(
        label='Логин', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username

    def save(self):
        cd = self.cleaned_data
        user = User.objects.create_user(
            username=cd['username'],
            password=cd['password1'],
            first_name=cd['first_name'],
            last_name=cd['last_name'],
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN)
        return user


class StaffLoginForm(forms.Form):
    username = forms.CharField(
        label='Логин',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    _user = None

    def clean(self):
        cd = super().clean()
        username = cd.get('username')
        password = cd.get('password')
        if username and password:
            user = authenticate(username=username, password=password)
            if user is None:
                raise forms.ValidationError('Неверный логин или пароль.')
            profile = None
            try:
                profile = user.staff_profile
            except Exception:
                pass
            if profile is None:
                raise forms.ValidationError('У вас нет доступа к панели сотрудника.')
            if not profile.is_active:
                raise forms.ValidationError('Ваш аккаунт заблокирован.')
            self._user = user
        return cd

    def get_user(self):
        return self._user


class StaffCreateForm(_PasswordMixin):
    first_name = forms.CharField(
        label='Имя', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label='Фамилия', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    username = forms.CharField(
        label='Логин', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        label='Роль',
        choices=StaffProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username

    def save(self):
        cd = self.cleaned_data
        user = User.objects.create_user(
            username=cd['username'],
            password=cd['password1'],
            first_name=cd['first_name'],
            last_name=cd['last_name'],
        )
        StaffProfile.objects.create(user=user, role=cd['role'])
        return user


class StaffEditForm(forms.Form):
    first_name = forms.CharField(
        label='Имя', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label='Фамилия', max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        label='Роль',
        choices=StaffProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    new_password = forms.CharField(
        label='Новый пароль',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Оставьте пустым, чтобы не менять'}),
    )

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        if profile:
            self.fields['first_name'].initial = profile.user.first_name
            self.fields['last_name'].initial = profile.user.last_name
            self.fields['role'].initial = profile.role

    def save(self, profile):
        cd = self.cleaned_data
        profile.user.first_name = cd['first_name']
        profile.user.last_name = cd['last_name']
        if cd.get('new_password'):
            profile.user.set_password(cd['new_password'])
        profile.user.save()
        profile.role = cd['role']
        profile.save()
        return profile
