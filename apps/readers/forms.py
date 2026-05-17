from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

from .models import Reader, BookRequest


class ReaderRegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=150, label='Имя')
    last_name = forms.CharField(max_length=150, label='Фамилия')
    username = forms.CharField(max_length=150, label='Логин')
    email = forms.EmailField(required=False, label='Email')
    phone = forms.CharField(max_length=50, required=False, label='Телефон')
    address = forms.CharField(required=False, label='Адрес', widget=forms.Textarea(attrs={'rows': 2}))
    password1 = forms.CharField(label='Пароль', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Повторите пароль', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-control'

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Пароли не совпадают.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data['username'],
            password=data['password1'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data.get('email', ''),
        )
        Reader.objects.create(
            user=user,
            phone=data.get('phone', ''),
            address=data.get('address', ''),
        )
        return user


class StyledAuthForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['password'].widget.attrs['class'] = 'form-control'
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'


class BookRequestForm(forms.ModelForm):
    class Meta:
        model = BookRequest
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Необязательное сообщение для библиотекаря…',
            }),
        }
        labels = {'message': 'Сообщение (необязательно)'}


class RequestStatusForm(forms.ModelForm):
    class Meta:
        model = BookRequest
        fields = ['status', 'librarian_note']
        widgets = {
            'librarian_note': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }
        labels = {
            'status': 'Статус',
            'librarian_note': 'Ответ библиотекаря',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].widget.attrs['class'] = 'form-select'
