"""Proline's AWS infrastructure.

Wiring and outputs only. The resources live in the modules beside this file:

    settings.py   every configured value, no defaults
    compute.py    the Lightsail instance, its static IP, key and firewall
    mail.py       the SES domain identity and a send-only credential
    dns.py        formatting the records to enter at GoDaddy (pure, no pulumi)

WHAT THIS DELIBERATELY DOES NOT MANAGE:

  * Off-box backups. There is no bucket here by choice -- the instance's daily
    Lightsail snapshot is the recovery point, so granularity is one day and a
    restore rebuilds the box. The bucket, the nightly-dump container and the
    admin staleness banner were removed together; `git log -- infra/backup` is
    where they are if that ever changes.

  * DNS. The domain is at GoDaddy -- see dns.py, and `pulumi stack output
    dns_records`.

  * SES production access. That is a support request reviewed by a person; there
    is no API for it. Until it is granted the account can only mail verified
    addresses, so offer emails to real clients go nowhere. Request it the day the
    domain verifies.

  * Anything inside the box beyond the OS. user-data.sh installs Docker, swap and
    unattended upgrades -- the parts identical on any rebuild. It does not write
    /srv/proline/.env, because user data is readable from the instance metadata
    endpoint and stored in plain text in this stack's state; a database password
    and SMTP credentials belong in neither. Those go in over SSH, once, by hand.
    See infra/DEPLOY.md.

Credentials for running this come from the AWS SDK's normal chain:

    aws configure --profile proline
    AWS_PROFILE=proline pulumi up

Keeping them in ~/.aws rather than in this repo means no .gitignore mistake and
no `git clean` accident can expose them, and nothing here has to be careful.
"""

# PEP 563: annotations stay strings, so `list[str] | None` and friends do not
# need Python 3.10 at runtime -- whatever python3 built the venv will do.
from __future__ import annotations

import pulumi

import compute
import dns
import mail
import settings

box = compute.provision(
    availability_zone=settings.AVAILABILITY_ZONE,
    bundle_id=settings.INSTANCE_BUNDLE,
    ssh_public_key=settings.SSH_PUBLIC_KEY,
    admin_ssh_cidr=settings.ADMIN_SSH_CIDR,
    tags=settings.TAGS,
)

sender = mail.provision(
    domain=settings.DOMAIN,
    from_address=settings.MAIL_FROM_ADDRESS,
    tags=settings.TAGS,
)


pulumi.export("static_ip", box.ip.ip_address)
pulumi.export("ssh", box.ip.ip_address.apply(lambda ip: f"ssh ubuntu@{ip}"))

# Output.unsecret() is load-bearing here, and it took a real deploy to find out.
#
# `dkim_signing_attributes` is one attribute bag that ALSO carries
# `domain_signing_private_key`, so the provider marks the whole bag secret -- and
# in Pulumi secretness is contagious through `apply`. Without unsecret, this export
# prints `[secret]` and DEPLOY.md's `pulumi stack output dns_records` shows nothing,
# for records that are public DNS by definition: they exist so the entire internet
# can read them.
#
# This is exactly the class of bug the mock-runtime check cannot see, because mocks
# return plain values and never reproduce the provider's secret annotations. Nothing
# private passes through here -- the tokens and the IP are both public -- but read
# that line again before copying this pattern anywhere the bag holds a real secret.
pulumi.export(
    "dns_records",
    pulumi.Output.unsecret(
        pulumi.Output.all(
            box.ip.ip_address, sender.identity.dkim_signing_attributes
        ).apply(
            lambda a: dns.records(
                domain=settings.DOMAIN, ip=a[0], dkim_tokens=a[1].get("tokens")
            )
        )
    ),
)

# Ready to paste into /srv/proline/.env on the box.
#
# Output.secret() wraps the OUTSIDE of the apply, not the inside. Returning a
# secret from within a lambda does not reliably mark the resulting export, and the
# failure is silent and bad: an unmarked export means the SMTP password sits in
# plaintext in the state file and prints on a bare `pulumi stack output`. Wrapped
# here, it is encrypted at rest and shown only on request:
#
#   pulumi stack output env_smtp --show-secrets
pulumi.export(
    "env_smtp",
    pulumi.Output.secret(
        pulumi.Output.all(
            sender.access_key.id, sender.access_key.ses_smtp_password_v4
        ).apply(
            lambda a: "\n".join(
                [
                    f"SMTP_HOST={settings.SMTP_HOST}",
                    f"SMTP_PORT={settings.SMTP_PORT}",
                    f"SMTP_USER={a[0]}",
                    f"SMTP_PASSWORD={a[1]}",
                    "SMTP_STARTTLS=true",
                ]
            )
        )
    ),
)
