import os
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from domains.models import TenantDomain


class Command(BaseCommand):
    help = 'Provision Apache HTTPS vhosts and Lets Encrypt certificates for active platform subdomains.'

    def add_arguments(self, parser):
        parser.add_argument('--domain', help='Provision one domain only.')
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if os.name == 'nt':
            raise CommandError('This command must run on the Linux production server.')

        queryset = TenantDomain.objects.filter(
            domain_type=TenantDomain.DomainType.PLATFORM_SUBDOMAIN,
            status=TenantDomain.Status.ACTIVE,
            is_verified=True,
        ).exclude(ssl_status=TenantDomain.SSLStatus.ACTIVE).order_by('created_at')
        if options['domain']:
            queryset = TenantDomain.objects.filter(domain=options['domain'])
        else:
            queryset = queryset[: options['limit']]

        count = 0
        for domain in queryset:
            count += 1
            self._provision_domain(domain, dry_run=options['dry_run'])
        self.stdout.write(self.style.SUCCESS(f'Processed {count} domain(s).'))

    def _run(self, command, *, dry_run=False):
        self.stdout.write('$ ' + ' '.join(command))
        if dry_run:
            return
        subprocess.run(command, check=True)

    def _provision_domain(self, domain, *, dry_run=False):
        hostname = domain.domain
        conf_name = f'pressnexa-{hostname}-le-ssl.conf'
        conf_path = Path('/etc/apache2/sites-available') / conf_name
        cert_dir = Path('/etc/letsencrypt/live') / hostname

        domain.ssl_status = TenantDomain.SSLStatus.PROVISIONING
        domain.ssl_provisioning_error = ''
        domain.save(update_fields=['ssl_status', 'ssl_provisioning_error', 'updated_at'])

        try:
            if not cert_dir.exists():
                self._run([
                    'certbot',
                    'certonly',
                    '--webroot',
                    '-w',
                    '/var/www/html',
                    '-d',
                    hostname,
                    '--non-interactive',
                    '--agree-tos',
                    '--keep-until-expiring',
                ], dry_run=dry_run)

            vhost = f'''<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName {hostname}

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://127.0.0.1:8085/
    ProxyPassReverse / http://127.0.0.1:8085/

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/{hostname}/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/{hostname}/privkey.pem
    Include /etc/letsencrypt/options-ssl-apache.conf
</VirtualHost>
</IfModule>
'''
            if not dry_run:
                conf_path.write_text(vhost)
            self._run(['a2ensite', conf_name], dry_run=dry_run)
            self._run(['apache2ctl', 'configtest'], dry_run=dry_run)
            self._run(['systemctl', 'reload', 'apache2'], dry_run=dry_run)

            domain.ssl_status = TenantDomain.SSLStatus.ACTIVE
            domain.ssl_provisioning_error = ''
            domain.save(update_fields=['ssl_status', 'ssl_provisioning_error', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(f'{hostname}: SSL active'))
        except Exception as exc:
            domain.ssl_status = TenantDomain.SSLStatus.FAILED
            domain.ssl_provisioning_error = str(exc)
            domain.save(update_fields=['ssl_status', 'ssl_provisioning_error', 'updated_at'])
            raise