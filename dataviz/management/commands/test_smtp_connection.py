from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Test plain SMTP connectivity without sending any email."

    def add_arguments(self, parser):
        parser.add_argument("--host", type=str, default="", help="SMTP host override")
        parser.add_argument("--port", type=int, default=0, help="SMTP port override")
        parser.add_argument("--username", type=str, default="", help="SMTP username override")
        parser.add_argument("--password", type=str, default="", help="SMTP password override")
        parser.add_argument("--timeout", type=int, default=0, help="SMTP timeout seconds override")
        parser.add_argument("--tls", action="store_true", help="Force TLS")
        parser.add_argument("--no-tls", action="store_true", help="Disable TLS")
        parser.add_argument("--ssl", action="store_true", help="Force SSL")
        parser.add_argument("--no-ssl", action="store_true", help="Disable SSL")
        parser.add_argument(
            "--skip-auth",
            action="store_true",
            help="Do not use SMTP username/password (connectivity-only mode)",
        )

    def handle(self, *args, **options):
        if options["tls"] and options["no_tls"]:
            raise CommandError("Use either --tls or --no-tls, not both.")
        if options["ssl"] and options["no_ssl"]:
            raise CommandError("Use either --ssl or --no-ssl, not both.")

        host = (options.get("host") or "").strip() or settings.EMAIL_HOST
        port = int(options.get("port") or 0) or settings.EMAIL_PORT
        username = (options.get("username") or "").strip() or settings.EMAIL_HOST_USER
        password = options.get("password") if options.get("password") != "" else settings.EMAIL_HOST_PASSWORD
        timeout = int(options.get("timeout") or 0) or settings.EMAIL_TIMEOUT

        if options.get("skip_auth"):
            username = ""
            password = ""

        if options["tls"]:
            use_tls = True
        elif options["no_tls"]:
            use_tls = False
        else:
            use_tls = settings.EMAIL_USE_TLS

        if options["ssl"]:
            use_ssl = True
        elif options["no_ssl"]:
            use_ssl = False
        else:
            use_ssl = settings.EMAIL_USE_SSL

        if use_tls and use_ssl:
            raise CommandError("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.")

        if not host or not port:
            raise CommandError("SMTP host/port are required. Set EMAIL_HOST and EMAIL_PORT or pass --host/--port.")

        self.stdout.write(
            f"Testing SMTP connectivity to {host}:{port} (tls={use_tls}, ssl={use_ssl}, timeout={timeout}s)"
        )

        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            fail_silently=False,
            host=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout=timeout,
        )

        try:
            connection.open()
        except Exception as exc:
            raise CommandError(f"SMTP connection failed: {exc}") from exc
        finally:
            connection.close()

        self.stdout.write(self.style.SUCCESS("SMTP connection successful."))
