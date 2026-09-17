from django import forms
from .models import Location, LocationType


def _type_choices():
    return list(LocationType.objects.values_list('code', 'name'))


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = [
            'name', 'type', 'address',
            'contact_person', 'contact_phone',
            'latitude', 'longitude',
            'is_active', 'is_public', 'notes',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'latitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'Кликните по карте'}),
            'longitude': forms.NumberInput(attrs={'step': 'any', 'placeholder': 'Кликните по карте'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type'].widget = forms.Select(choices=_type_choices())
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs['class'] = 'form-control'
            else:
                field.widget.attrs['class'] = 'form-control'


class LocationTypeForm(forms.ModelForm):
    class Meta:
        model = LocationType
        fields = ['code', 'name', 'is_open']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр. KINDERGARTEN'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Детский сад'}),
            'is_open': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].upper().replace(' ', '_')
