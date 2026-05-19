from django import forms
from .models import Book


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
        for name, field in self.fields.items():
            if name == 'cover_clear':
                continue
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            elif isinstance(field.widget, (forms.Textarea, forms.ClearableFileInput)):
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('cover_clear') and instance.cover:
            instance.cover.delete(save=False)
            instance.cover = None
        if commit:
            instance.save()
        return instance


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
