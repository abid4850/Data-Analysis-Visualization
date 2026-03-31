from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string


class Command(BaseCommand):
    help = "Send a password reset test email using configured SMTP settings."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, required=True, help="Recipient email address")
        parser.add_argument(
            "--create-user",
            action="store_true",
            help="Create an active user account if no user exists for the email",
        )
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help="Username to use when creating a user (optional)",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default="",
            help="Override reset link domain (defaults to PASSWORD_RESET_DOMAIN_OVERRIDE)",
        )
        parser.add_argument(
            "--https",
            action="store_true",
            help="Force https links (overrides PASSWORD_RESET_USE_HTTPS)",
        )
        parser.add_argument(
            "--http",
            action="store_true",
            help="Force http links (overrides PASSWORD_RESET_USE_HTTPS)",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip().lower()
        if not email:
            raise CommandError("--email is required.")

        force_https = bool(options.get("https"))
        force_http = bool(options.get("http"))
        if force_https and force_http:
            raise CommandError("Use either --https or --http, not both.")

        configured_domain = (settings.PASSWORD_RESET_DOMAIN_OVERRIDE or "").strip()
        domain_override = (options.get("domain") or configured_domain).strip()
        if not domain_override:
            raise CommandError(
                "No reset domain configured. Set PASSWORD_RESET_DOMAIN_OVERRIDE or pass --domain."
            )

        if force_https:
            use_https = True
        elif force_http:
            use_https = False
        else:
            use_https = bool(settings.PASSWORD_RESET_USE_HTTPS)

        user_model = get_user_model()
        existing_users = user_model._default_manager.filter(email__iexact=email, is_active=True)

        if not existing_users.exists():
            if not options.get("create_user"):
                raise CommandError(
                    "No active user found for this email. Use --create-user to create a test account."
                )

            username_seed = (options.get("username") or email.split("@", maxsplit=1)[0] or "reset-user").strip()
            username_seed = username_seed[:120] or "reset-user"
            username = username_seed
            suffix = 1
            while user_model._default_manager.filter(username=username).exists():
                suffix += 1
                username = f"{username_seed}-{suffix}"[:150]

            temporary_password = get_random_string(32)
            user_model._default_manager.create_user(
                username=username,
                email=email,
                password=temporary_password,
                is_active=True,
            )
            self.stdout.write(self.style.WARNING(f"Created active test user: {username}"))

        form = PasswordResetForm({"email": email})
        if not form.is_valid():
            raise CommandError(f"Invalid email: {email}")

        form.save(
            use_https=use_https,
            from_email=settings.PASSWORD_RESET_FROM_EMAIL,
            request=None,
            domain_override=domain_override,
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
        )

        scheme = "https" if use_https else "http"
        self.stdout.write(
            self.style.SUCCESS(
                f"Password reset email sent to {email} using {scheme}://{domain_override} from {settings.PASSWORD_RESET_FROM_EMAIL}"
            )
        )
