# bookings/forms.py (REPLACE EXISTING)
from django import forms
from django.utils import timezone
from datetime import timedelta
from .models import Booking, PolicyException, RECURRENCE_FREQUENCY
from labs.models import Lab


class BookingForm(forms.ModelForm):
    """Enhanced form with recurring booking support"""
    
    # Recurring fields
    create_recurring = forms.BooleanField(
        required=False,
        label="Create Recurring Booking",
        help_text="Enable to create multiple bookings on a schedule"
    )
    recurrence_frequency = forms.ChoiceField(
        required=False,
        choices=[('', '---')] + RECURRENCE_FREQUENCY[1:],  # Exclude 'none'
        label="Repeat Every",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    recurrence_end_date = forms.DateField(
        required=False,
        label="Until",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        help_text="Last date for recurring bookings"
    )
    
    # Policy exception
    request_exception = forms.BooleanField(
        required=False,
        label="Request Policy Exception",
        help_text="Check if this booking exceeds normal limits"
    )
    exception_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why this exception is needed'
        }),
        label="Exception Reason"
    )

    class Meta:
        model = Booking
        fields = ['lab', 'start', 'end', 'purpose']

        widgets = {
            'lab': forms.Select(attrs={
                'class': 'form-select',
                'placeholder': 'Select a lab'
            }),
            'start': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'end': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'purpose': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter purpose of booking (optional)'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Only show available labs
        self.fields['lab'].queryset = Lab.objects.all()

        # Hide recurring options for students
        if self.user and not self.user.can_create_recurring:
            self.fields['create_recurring'].widget = forms.HiddenInput()
            self.fields['recurrence_frequency'].widget = forms.HiddenInput()
            self.fields['recurrence_end_date'].widget = forms.HiddenInput()
        
        # If editing, disable some fields
        if self.instance.pk:
            self.fields['create_recurring'].widget = forms.HiddenInput()
            self.fields['recurrence_frequency'].widget = forms.HiddenInput()
            self.fields['recurrence_end_date'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start')
        end = cleaned_data.get('end')
        lab = cleaned_data.get('lab')
        create_recurring = cleaned_data.get('create_recurring')
        recurrence_frequency = cleaned_data.get('recurrence_frequency')
        recurrence_end_date = cleaned_data.get('recurrence_end_date')
        request_exception = cleaned_data.get('request_exception')
        exception_reason = cleaned_data.get('exception_reason')

        # Basic validations
        if not lab:
            raise forms.ValidationError("Please select a lab.")
        if not start or not end:
            raise forms.ValidationError("Start and end times are required.")

        if end <= start:
            raise forms.ValidationError("End time must be after start time.")
        
        if start < timezone.now():
            raise forms.ValidationError("Start time must be in the future.")

        # Recurring validation
        if create_recurring:
            if not self.user or not self.user.can_create_recurring:
                raise forms.ValidationError("You don't have permission to create recurring bookings.")
            
            if not recurrence_frequency:
                raise forms.ValidationError("Please select a recurrence frequency.")
            
            if not recurrence_end_date:
                raise forms.ValidationError("Please specify when recurring bookings should end.")
            
            if recurrence_end_date <= start.date():
                raise forms.ValidationError("Recurrence end date must be after the start date.")
            
            # Limit recurring bookings to reasonable timeframe
            max_date = start.date() + timedelta(days=365)
            if recurrence_end_date > max_date:
                raise forms.ValidationError("Recurring bookings cannot exceed 1 year.")

        # Policy exception validation
        if request_exception and not exception_reason:
            raise forms.ValidationError("Please provide a reason for the policy exception.")

        # Conflict check
        from .models import Booking
        overlapping = Booking.objects.filter(
            lab=lab,
            start__lt=end,
            end__gt=start
        ).exclude(status__in=["cancelled", "rejected"])

        if self.instance.pk:
            overlapping = overlapping.exclude(pk=self.instance.pk)

        if overlapping.exists():
            raise forms.ValidationError(
                "The selected lab is already booked during this time. "
                "Please choose another time slot."
            )

        return cleaned_data


class BookingUpdateForm(forms.ModelForm):
    """Form for updating existing bookings"""
    
    update_future = forms.BooleanField(
        required=False,
        label="Update All Future Occurrences",
        help_text="Apply changes to all future recurring bookings"
    )
    
    class Meta:
        model = Booking
        fields = ['start', 'end', 'purpose', 'admin_notes']
        widgets = {
            'start': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'end': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
            'purpose': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'admin_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Only admins can edit admin_notes
        if self.user and not self.user.can_approve_bookings:
            self.fields.pop('admin_notes')
        
        # Hide update_future if not recurring
        if not self.instance.is_recurring:
            self.fields['update_future'].widget = forms.HiddenInput()


class PolicyExceptionForm(forms.ModelForm):
    """Form for requesting policy exceptions"""
    
    class Meta:
        model = PolicyException
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Explain why this exception is necessary...'
            })
        }