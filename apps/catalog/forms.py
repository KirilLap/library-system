from django import forms
from .models import Book, Genre, Language


def _genre_choices():
    choices = [('', '— Жанр —')] + list(Genre.objects.values_list('code', 'name'))
    return choices


def _language_choices():
    choices = [('', '— Язык —')] + list(Language.objects.values_list('code', 'name'))
    return choices


class BookForm(forms.ModelForm):
    cover_clear = forms.BooleanField(required=False, label='Удалить обложку')

    class Meta:
        model = Book
        fields = [
            'inventory_number', 'barcode', 'title', 'author', 'year',
            'publisher', 'genre', 'language', 'description', 'isbn', 'status',
            'cover',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'cover': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genre'].widget = forms.Select(choices=_genre_choices())
        self.fields['language'].widget = forms.Select(choices=_language_choices())
        for name, field in self.fields.items():
            if name == 'cover_clear':
                continue
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            elif isinstance(field.widget, (forms.Textarea, forms.ClearableFileInput)):
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cd = super().clean()
        title = (cd.get('title') or '').strip()
        author = (cd.get('author') or '').strip()
        if title and author:
            qs = Book.objects.filter(title__iexact=title, author__iexact=author)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                dupe = qs.first()
                self.duplicate_warning = (
                    f'Возможный дубликат: книга «{dupe.title}» того же автора '
                    f'уже есть в каталоге (инв. {dupe.inventory_number}).'
                )
        return cd

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('cover_clear') and instance.cover:
            instance.cover.delete(save=False)
            instance.cover = None
        if commit:
            instance.save()
        return instance


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
