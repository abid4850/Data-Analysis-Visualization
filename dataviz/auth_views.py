import re

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.contrib.auth.views import PasswordResetView
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.urls import reverse_lazy

from .auth_forms import EmailAuthenticationForm


class EmailLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm

    def get_success_url(self):
        target_url = super().get_success_url()
        download_match = re.fullmatch(r"/datasets/store/(?P<dataset_id>\d+)/download/?", target_url)

        if download_match:
            dataset_id = download_match.group("dataset_id")
            return f"{reverse('dataviz:datasets')}?download={dataset_id}"

        return target_url


class ProductionPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        form.save(
            use_https=settings.PASSWORD_RESET_USE_HTTPS or self.request.is_secure(),
            from_email=settings.PASSWORD_RESET_FROM_EMAIL,
            request=self.request,
            token_generator=self.token_generator,
            email_template_name=self.email_template_name,
            subject_template_name=self.subject_template_name,
            html_email_template_name=self.html_email_template_name,
            extra_email_context=self.extra_email_context,
            domain_override=settings.PASSWORD_RESET_DOMAIN_OVERRIDE or None,
        )
        return HttpResponseRedirect(self.get_success_url())
