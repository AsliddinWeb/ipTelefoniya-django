# apps/users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class LoginForm(forms.Form):
    """Custom Login Form"""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter username or email',
            'id': 'username',
            'required': True
        }),
        label='Username'
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control pe-5 password-input',
            'placeholder': 'Enter password',
            'id': 'password-input',
            'required': True
        }),
        label='Password'
    )

    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'auth-remember-check'
        }),
        label='Remember me'
    )


class SignupForm(UserCreationForm):
    """Custom Signup Form"""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter email address',
            'id': 'useremail'
        })
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Username field styling
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter username',
            'id': 'username'
        })

        # Password1 field styling
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control pe-5 password-input',
            'placeholder': 'Enter password',
            'id': 'password-input',
            'onpaste': 'return false',
            'pattern': '(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}'
        })

        # Password2 field styling
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control pe-5 password-input',
            'placeholder': 'Confirm password',
            'id': 'password-confirm'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user