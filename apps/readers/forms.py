from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

from .models import Reader, BookRequest


def _nearest_location_field():
    """Необязательный выбор ближайшего библиопункта (только публичные и активные)."""
    return forms.ModelChoiceField(
        queryset=None, required=False, label='Ближайший библиопункт',
        empty_label='— не выбран —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


def _birth_year_field():
    return forms.IntegerField(
        label='Год рождения', min_value=1900,
        widget=forms.NumberInput(attrs={'placeholder': '2005'}),
    )


class _ReaderFormBase(forms.Form):
    """Общие поля читателя: ФИО, год рождения, ближайший библиопункт."""

    last_name = forms.CharField(max_length=150, label='Фамилия')
    first_name = forms.CharField(max_length=150, label='Имя')
    birth_year = _birth_year_field()
    nearest_location = _nearest_location_field()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.locations.models import Location
        self.fields['nearest_location'].queryset = Location.objects.filter(
            is_active=True, is_public=True,
        ).order_by('name')
        for field in self.fields.values():
            if not isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-control'

    def clean_birth_year(self):
        from django.utils import timezone
        year = self.cleaned_data['birth_year']
        if year > timezone.now().year:
            raise forms.ValidationError('Год рождения не может быть в будущем.')
        return year

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Этот логин уже занят.')
        return username

    def _create_reader(self, username, password, must_change_password=False, card_id=None):
        from .models import generate_card_id
        data = self.cleaned_data
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=data['first_name'],
            last_name=data['last_name'],
        )
        Reader.objects.create(
            user=user,
            card_id=card_id or generate_card_id(),
            birth_year=data['birth_year'],
            nearest_location=data.get('nearest_location'),
            must_change_password=must_change_password,
        )
        return user


class ReaderRegistrationForm(_ReaderFormBase):
    """Самостоятельная регистрация читателя (и регистрация работником библиопункта)."""

    username = forms.CharField(max_length=150, label='Логин')
    password1 = forms.CharField(label='Пароль', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Повторите пароль', widget=forms.PasswordInput)

    field_order = ['last_name', 'first_name', 'birth_year', 'nearest_location',
                   'username', 'password1', 'password2']

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Пароли не совпадают.')
        return cleaned

    def save(self):
        return self._create_reader(self.cleaned_data['username'], self.cleaned_data['password1'])


class ReaderCreateForm(_ReaderFormBase):
    """Читателя вносит сотрудник библиотеки. Логин и временный пароль создаются
    автоматически (это ID читателя), при первом входе читатель задаёт свой пароль."""

    field_order = ['last_name', 'first_name', 'birth_year', 'nearest_location']

    def save(self):
        from .models import generate_card_id
        card_id = generate_card_id()
        return self._create_reader(card_id, card_id, must_change_password=True, card_id=card_id)


class StyledAuthForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['password'].widget.attrs['class'] = 'form-control'
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'


class ReaderProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label='Имя', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, label='Фамилия', widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Reader
        fields = ['birth_year', 'nearest_location']
        widgets = {
            'birth_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2005'}),
            'nearest_location': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'birth_year': 'Год рождения',
            'nearest_location': 'Ближайший библиопункт',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from apps.locations.models import Location
        self.fields['nearest_location'].queryset = Location.objects.filter(
            is_active=True, is_public=True,
        ).order_by('name')
        self.fields['nearest_location'].empty_label = '— не выбран —'
        self.fields['nearest_location'].required = False
        self.fields['birth_year'].required = False
        self.order_fields(['last_name', 'first_name', 'birth_year', 'nearest_location'])
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name

    def clean_birth_year(self):
        from django.utils import timezone
        year = self.cleaned_data.get('birth_year')
        if year is not None and not (1900 <= year <= timezone.now().year):
            raise forms.ValidationError('Укажите корректный год рождения.')
        return year

    def save(self, commit=True):
        reader = super().save(commit=commit)
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.save()
        return reader


class BookRequestForm(forms.ModelForm):
    class Meta:
        model = BookRequest
        fields = ['preferred_location', 'message']
        widgets = {
            'preferred_location': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Необязательное сообщение для библиотекаря…',
            }),
        }
        labels = {
            'preferred_location': 'Где забрать книгу',
            'message': 'Сообщение (необязательно)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.locations.models import Location
        self.fields['preferred_location'].queryset = Location.objects.filter(is_active=True)
        self.fields['preferred_location'].empty_label = '— Уточнит библиотекарь —'
        self.fields['preferred_location'].required = False


class FreeBookRequestForm(forms.ModelForm):
    class Meta:
        model = BookRequest
        fields = ['requested_title', 'requested_author', 'preferred_location', 'message']
        widgets = {
            'requested_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Гарри Поттер и философский камень',
            }),
            'requested_author': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Дж. К. Роулинг',
            }),
            'preferred_location': forms.Select(attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'Дополнительная информация (необязательно)',
            }),
        }
        labels = {
            'requested_title': 'Название книги',
            'requested_author': 'Автор',
            'preferred_location': 'Где забрать книгу',
            'message': 'Комментарий',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.locations.models import Location
        self.fields['preferred_location'].queryset = Location.objects.filter(is_active=True)
        self.fields['preferred_location'].empty_label = '— Уточнит библиотекарь —'
        self.fields['preferred_location'].required = False

    def clean_requested_title(self):
        title = self.cleaned_data.get('requested_title', '').strip()
        if not title:
            raise forms.ValidationError('Укажите название книги.')
        return title


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
