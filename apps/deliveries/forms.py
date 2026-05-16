from django import forms
from .models import DeliveryBatch


class DeliveryBatchForm(forms.ModelForm):
    class Meta:
        model = DeliveryBatch
        fields = ['location', 'delivery_date', 'note']
        widgets = {
            'delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.locations.models import Location
        self.fields['location'].queryset = Location.objects.filter(is_active=True)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs['class'] = 'form-select'
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            else:
                widget.attrs['class'] = 'form-control'


class AddBookForm(forms.Form):
    inventory_number = forms.CharField(
        max_length=50,
        label='Инв. номер',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите инв. номер и нажмите Enter',
            'autocomplete': 'off',
            'autofocus': True,
        }),
    )
