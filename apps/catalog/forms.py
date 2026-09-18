from django import forms
from django.utils.translation import gettext as _
from .models import Book, BookTitle, Genre, Language


def _genre_choices():
    choices = [('', _('— Жанр —'))] + [
        (code, _(name)) for code, name in Genre.objects.values_list('code', 'name')
    ]
    return choices


def _language_choices():
    choices = [('', _('— Язык —'))] + [
        (code, _(name)) for code, name in Language.objects.values_list('code', 'name')
    ]
    return choices


def _style_fields(form, skip=()):
    for name, field in form.fields.items():
        if name in skip:
            continue
        if isinstance(field.widget, forms.Select):
            field.widget.attrs['class'] = 'form-select'
        else:
            field.widget.attrs['class'] = 'form-control'


class BookTitleForm(forms.ModelForm):
    """Редактирование библиографических данных (общих для всех экземпляров)."""
    cover_clear = forms.BooleanField(required=False, label='Удалить обложку')

    class Meta:
        model = BookTitle
        fields = [
            'title', 'author', 'year', 'publisher',
            'genre', 'language', 'description', 'isbn', 'cover',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'cover': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genre'].widget = forms.Select(choices=_genre_choices())
        self.fields['language'].widget = forms.Select(choices=_language_choices())
        _style_fields(self, skip=('cover_clear',))

    def clean(self):
        cd = super().clean()
        title = (cd.get('title') or '').strip()
        author = (cd.get('author') or '').strip()
        if title and author:
            qs = BookTitle.objects.filter(title__iexact=title, author__iexact=author)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                dupe = qs.first()
                self.duplicate_warning = (
                    f'Возможный дубликат: книга «{dupe.title}» того же автора уже есть '
                    f'в каталоге ({dupe.copies_count} экз.) — рассмотрите добавление экземпляра к ней.'
                )
                self.duplicate_title = dupe
        return cd

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('cover_clear') and instance.cover:
            instance.cover.delete(save=False)
            instance.cover = None
        if commit:
            instance.save()
        return instance


class BookCopyForm(forms.ModelForm):
    """Экземпляр (инв. номер, статус) — привязывается к существующему BookTitle."""

    class Meta:
        model = Book
        fields = ['inventory_number', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class NewBookForm(forms.Form):
    """Создание новой книги «с нуля»: библиографическая запись + первый экземпляр."""

    title = forms.CharField(max_length=500, label='Название')
    author = forms.CharField(max_length=300, label='Автор', required=False)
    year = forms.IntegerField(label='Год', required=False)
    publisher = forms.CharField(max_length=300, label='Издательство', required=False)
    genre = forms.ChoiceField(label='Жанр', choices=[], required=False)
    language = forms.ChoiceField(label='Язык', choices=[], required=False)
    description = forms.CharField(label='Описание', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    isbn = forms.CharField(max_length=20, label='ISBN', required=False)
    cover = forms.ImageField(label='Обложка', required=False)
    inventory_number = forms.CharField(max_length=50, label='Инв. номер')
    status = forms.ChoiceField(label='Статус', choices=Book.STATUS_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genre'].choices = _genre_choices()
        self.fields['language'].choices = _language_choices()
        self.fields['genre'].initial = 'OTHER'
        self.fields['language'].initial = 'RU'
        _style_fields(self)

    def clean_inventory_number(self):
        inv = self.cleaned_data['inventory_number'].strip()
        if Book.objects.filter(inventory_number=inv).exists():
            raise forms.ValidationError('Книга с таким инвентарным номером уже есть в каталоге.')
        return inv

    def clean(self):
        cd = super().clean()
        title = (cd.get('title') or '').strip()
        author = (cd.get('author') or '').strip()
        if title and author:
            dupe = BookTitle.objects.filter(title__iexact=title, author__iexact=author).first()
            if dupe:
                self.duplicate_title = dupe
        return cd

    def save(self):
        cd = self.cleaned_data
        book_title = BookTitle.objects.create(
            title=cd['title'].strip(),
            author=cd.get('author', '').strip(),
            year=cd.get('year'),
            publisher=cd.get('publisher', ''),
            genre=cd.get('genre') or 'OTHER',
            language=cd.get('language') or 'RU',
            description=cd.get('description', ''),
            isbn=cd.get('isbn', ''),
            cover=cd.get('cover'),
        )
        return Book.objects.create(
            book_title=book_title,
            inventory_number=cd['inventory_number'],
            status=cd.get('status') or 'IN_LIBRARY',
        )


class GenreForm(forms.ModelForm):
    class Meta:
        model = Genre
        fields = ['code', 'name']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр. SCIENCE'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Научно-популярная'}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].upper().replace(' ', '_')


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        fields = ['code', 'name']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр. KK'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Казахский'}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].upper().replace(' ', '_')


class MARCImportForm(forms.Form):
    file = forms.FileField(
        label='MARC файл',
        help_text='Поддерживаются форматы .mrc и .marc (MARC21)',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs['class'] = 'form-control'
        self.fields['file'].widget.attrs['accept'] = '.mrc,.marc'


class ExcelImportForm(forms.Form):
    file = forms.FileField(
        label='Excel файл',
        help_text='Формат .xlsx',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs['class'] = 'form-control'
        self.fields['file'].widget.attrs['accept'] = '.xlsx'
