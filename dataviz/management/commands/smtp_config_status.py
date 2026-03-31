from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _is_set(value):
    return bool(str(value).strip()) if value is not None else False


def _yes_no(value):
    return "yes" if value else "no"


class Command(BaseCommand):
    help = "Show SMTP readiness with redacted credential status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with CommandError if SMTP is not production-ready.",
        )

    def handle(self, *args, **options):
        backend = getattr(settings, "EMAIL_BACKEND", "")
        host = getattr(settings, "EMAIL_HOST", "")
        port = getattr(settings, "EMAIL_PORT", 0)
        username = getattr(settings, "EMAIL_HOST_USER", "")
        password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        use_tls = bool(getattr(settings, "EMAIL_USE_TLS", False))
        use_ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
        timeout = getattr(settings, "EMAIL_TIMEOUT", 20)

        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        server_email = getattr(settings, "SERVER_EMAIL", "")
        reset_from = getattr(settings, "PASSWORD_RESET_FROM_EMAIL", "")
        reset_use_https = bool(getattr(settings, "PASSWORD_RESET_USE_HTTPS", False))
        reset_domain = getattr(settings, "PASSWORD_RESET_DOMAIN_OVERRIDE", "")

        checks = {
            "smtp_backend": backend == "django.core.mail.backends.smtp.EmailBackend",
            "host_set": _is_set(host),
            "port_set": int(port or 0) > 0,
            "security_valid": not (use_tls and use_ssl),
            "auth_pair_valid": (_is_set(username) and _is_set(password)) or (not _is_set(username) and not _is_set(password)),
            "default_from_set": _is_set(default_from),
            "reset_from_set": _is_set(reset_from),
            "reset_domain_set": _is_set(reset_domain),
        }

        smtp_ready = all(
            [
                checks["smtp_backend"],
                checks["host_set"],
                checks["port_set"],
                checks["security_valid"],
                checks["auth_pair_valid"],
                checks["default_from_set"],
            ]
        )
        password_reset_ready = smtp_ready and checks["reset_from_set"] and checks["reset_domain_set"] and reset_use_https

        self.stdout.write("SMTP Configuration Status")
        self.stdout.write("-------------------------")
        self.stdout.write(f"EMAIL_BACKEND: {backend}")
        self.stdout.write(f"EMAIL_HOST: {host or '[missing]'}")
        self.stdout.write(f"EMAIL_PORT: {port}")
        self.stdout.write(f"EMAIL_USE_TLS: {_yes_no(use_tls)}")
        self.stdout.write(f"EMAIL_USE_SSL: {_yes_no(use_ssl)}")
        self.stdout.write(f"EMAIL_TIMEOUT: {timeout}")
        self.stdout.write(f"EMAIL_HOST_USER: {'[set]' if _is_set(username) else '[missing]'}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD: {'[set]' if _is_set(password) else '[missing]'}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {default_from or '[missing]'}")
        self.stdout.write(f"SERVER_EMAIL: {server_email or '[missing]'}")
        self.stdout.write(f"PASSWORD_RESET_FROM_EMAIL: {reset_from or '[missing]'}")
        self.stdout.write(f"PASSWORD_RESET_USE_HTTPS: {_yes_no(reset_use_https)}")
        self.stdout.write(f"PASSWORD_RESET_DOMAIN_OVERRIDE: {reset_domain or '[missing]'}")
        self.stdout.write(f"SMTP_READY: {_yes_no(smtp_ready)}")
        self.stdout.write(f"PASSWORD_RESET_READY: {_yes_no(password_reset_ready)}")

        issues = []
        if not checks["smtp_backend"]:
            issues.append("EMAIL_BACKEND is not django.core.mail.backends.smtp.EmailBackend")
        if not checks["host_set"]:
            issues.append("EMAIL_HOST is missing")
        if not checks["port_set"]:
            issues.append("EMAIL_PORT must be greater than 0")
        if not checks["security_valid"]:
            issues.append("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be true")
        if not checks["auth_pair_valid"]:
            issues.append("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must both be set or both be empty")
        if not checks["default_from_set"]:
            issues.append("DEFAULT_FROM_EMAIL is missing")
        if not checks["reset_from_set"]:
            issues.append("PASSWORD_RESET_FROM_EMAIL is missing")
        if not checks["reset_domain_set"]:
            issues.append("PASSWORD_RESET_DOMAIN_OVERRIDE is missing")
        if not reset_use_https:
            issues.append("PASSWORD_RESET_USE_HTTPS is false")

        if issues:
            self.stdout.write("\nReadiness issues:")
            for issue in issues:
                self.stdout.write(f"- {issue}")

        if options.get("strict") and not smtp_ready:
            raise CommandError("SMTP is not ready. Resolve listed readiness issues.")
