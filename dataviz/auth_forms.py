from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Invalid email or password. Please try again.",
    }

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "email",
                "placeholder": "name@company.com",
            }
        ),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip()
