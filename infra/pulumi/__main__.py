"""Proline's AWS infrastructure.

What this manages: the Lightsail instance and its static IP and firewall, the
SSH key pair, the backup bucket and its access key, the SES domain identity, and
the IAM user whose only power is to send mail through SES.

What this deliberately does NOT manage, and why:

  * DNS. The domain is at GoDaddy, and the community Terraform/Pulumi providers
    for it are a dependency this project does not need for seven records typed
    once. The program prints exactly what to enter -- see `pulumi stack output
    dns_records`.

  * SES production access. That is a support request reviewed by a person; there
    is no API for it. Until it is granted the account can only mail verified
    addresses, so offer emails to real clients go nowhere. Request it the day
    the domain verifies.

  * Anything inside the box beyond the OS. user-data.sh installs Docker, swap
    and unattended upgrades -- the parts that are identical on any rebuild. It
    does not write /srv/proline/.env, because user data is readable from the
    instance metadata endpoint and is stored in plain text in this stack's
    state; a database password and SMTP credentials do not belong in either.
    Those two files are written over SSH, by hand, once. See infra/DEPLOY.md.

Credentials for running this come from the AWS SDK's normal chain -- a named
profile is the right answer:

    aws configure --profile proline        # the IAM admin keys, in ~/.aws
    AWS_PROFILE=proline pulumi up

Keeping them in ~/.aws rather than infra/.env means no .gitignore mistake and no
`git clean` accident can ever expose them, and nothing in this repo has to be
careful.
"""

import json
import pathlib

import pulumi
import pulumi_aws as aws

config = pulumi.Config()

# The domain, so the SES identity and the printed DNS records agree with the
# Caddyfile without anyone editing three files.
DOMAIN = config.get("domain") or "prolinecleaningsolutions.ca"

# Where SSH may come from. Required rather than defaulted: `0.0.0.0/0` is a
# reasonable choice for someone on a dynamic residential address, but it should
# be a choice that was made, not one that was inherited.
ADMIN_CIDR = config.require("adminSshCidr")

# Your own public key, uploaded. The alternative -- letting Lightsail generate
# the pair -- puts a private key in this stack's state and in your Downloads
# folder. This way the private half never leaves your machine.
SSH_PUBLIC_KEY = config.require("sshPublicKey")

# 2 GB / 2 vCPU / 60 GB / 3 TB, $12 a month.
#
# VERIFY THIS ONE VALUE before the first `pulumi up`. Bundle IDs are runtime
# data with no data source to query, AWS renamed the suffix from `_2_0` to
# `_3_0` when the current pricing landed, and a wrong value fails with an
# unhelpful API error:
#
#   aws lightsail get-bundles --region ca-central-1 \
#     --query 'bundles[?ramSizeInGb==`2.0`].[bundleId,price,ramSizeInGb,cpuCount]' \
#     --output table
#
# It is config rather than a constant so correcting it is one command.
INSTANCE_BUNDLE = config.get("instanceBundle") or "small_3_0"

# 5 GB, 25 GB transfer, $1 a month. A nightly gzipped dump of a lead table takes
# years to outgrow this; the app warns on /admin if the last one is stale.
BUCKET_BUNDLE = config.get("bucketBundle") or "small_1_0"

AVAILABILITY_ZONE = config.get("availabilityZone") or "ca-central-1a"

tags = {"Project": "proline", "ManagedBy": "pulumi"}


# --- the box ------------------------------------------------------------------

key_pair = aws.lightsail.KeyPair(
    "proline-ssh",
    name="proline-ssh",
    public_key=SSH_PUBLIC_KEY,
    tags=tags,
)

instance = aws.lightsail.Instance(
    "proline-prod",
    name="proline-prod",
    availability_zone=AVAILABILITY_ZONE,
    # OS only. The Bitnami and "Docker" blueprints arrive with their own Apache
    # or nginx already bound to port 80, which is where Caddy needs to be.
    blueprint_id="ubuntu_24_04",
    bundle_id=INSTANCE_BUNDLE,
    key_pair_name=key_pair.name,
    # IPv4 only, to match the DNS plan. Dualstack would hand out an IPv6 address
    # that nothing resolves to, which looks like a broken site to exactly the
    # people whose networks prefer IPv6.
    ip_address_type="ipv4",
    user_data=pathlib.Path(__file__).with_name("user-data.sh").read_text(),
    # Whole-disk snapshots, ~$0.60/month. The bucket backup covers the database;
    # this covers everything else on the box, including the Caddy certificate
    # store and the two .env files that exist nowhere else.
    add_on=aws.lightsail.InstanceAddOnArgs(
        type="AutoSnapshot",
        snapshot_time="07:00",  # UTC; 03:00 in Montreal
        status="Enabled",
    ),
    tags=tags,
)

static_ip = aws.lightsail.StaticIp("proline-ip", name="proline-ip")

aws.lightsail.StaticIpAttachment(
    "proline-ip-attachment",
    static_ip_name=static_ip.name,
    instance_name=instance.name,
)

# This resource REPLACES the instance's port rules rather than adding to them,
# which is what makes it useful: Lightsail opens 22 to the world by default, and
# declaring the full set here closes that on the first `pulumi up`.
aws.lightsail.InstancePublicPorts(
    "proline-ports",
    instance_name=instance.name,
    port_infos=[
        aws.lightsail.InstancePublicPortsPortInfoArgs(
            protocol="tcp", from_port=80, to_port=80, cidrs=["0.0.0.0/0"]
        ),
        aws.lightsail.InstancePublicPortsPortInfoArgs(
            protocol="tcp", from_port=443, to_port=443, cidrs=["0.0.0.0/0"]
        ),
        aws.lightsail.InstancePublicPortsPortInfoArgs(
            protocol="tcp", from_port=22, to_port=22, cidrs=[ADMIN_CIDR]
        ),
    ],
)


# --- where the backups land ---------------------------------------------------

bucket = aws.lightsail.Bucket(
    "proline-backups",
    name="proline-backups",
    bundle_id=BUCKET_BUNDLE,
    # Refuse to delete a bucket that still holds objects. `pulumi destroy`
    # should not be able to take the backups with it.
    force_delete=False,
    tags=tags,
)

# A Lightsail bucket has its own access keys, scoped to that bucket. Worth
# preferring over an IAM user with an S3 policy: this credential cannot reach
# anything else in the account even if the box is compromised, and there is no
# policy document to get subtly wrong.
bucket_key = aws.lightsail.BucketAccessKey(
    "proline-backups-key", bucket_name=bucket.name
)


# --- mail ---------------------------------------------------------------------

# Easy DKIM: AWS holds the private key and gives us three CNAMEs to publish.
email_identity = aws.sesv2.EmailIdentity(
    "proline-domain",
    email_identity=DOMAIN,
    dkim_signing_attributes=aws.sesv2.EmailIdentityDkimSigningAttributesArgs(
        next_signing_key_length="RSA_2048_BIT"
    ),
    tags=tags,
)

# The app's mail credential. Send-only, and only as this domain: if the SMTP
# password leaks from the box, what it buys is the ability to send mail that
# already looks like ours -- not to read SES, change identities, or touch
# anything else.
mail_user = aws.iam.User("proline-mailer", name="proline-mailer", tags=tags)

aws.iam.UserPolicy(
    "proline-mailer-policy",
    user=mail_user.name,
    # The FromAddress condition must match MAIL_FROM in /srv/proline/.env. It
    # compares the address only, so the display name in
    # `Proline Cleaning Solutions <info@...>` is fine -- but if you ever change
    # the sending address and SES starts answering AccessDenied, this is why.
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ses:SendRawEmail", "ses:SendEmail"],
                    "Resource": "*",
                    "Condition": {
                        "StringEquals": {"ses:FromAddress": f"info@{DOMAIN}"}
                    },
                }
            ],
        }
    ),
)

mail_key = aws.iam.AccessKey("proline-mailer-key", user=mail_user.name)


# --- what you need next -------------------------------------------------------

pulumi.export("static_ip", static_ip.ip_address)
pulumi.export("ssh", static_ip.ip_address.apply(lambda ip: f"ssh ubuntu@{ip}"))
pulumi.export("bucket_name", bucket.name)

# Both blocks below are ready to paste into the two files on the box.
#
# Output.secret() wraps the OUTSIDE of the apply, not the inside. Returning a
# secret from within a lambda does not reliably mark the resulting export, and
# the failure is silent and bad: an unmarked export means the SMTP password sits
# in plaintext in the stack's state file and prints on a bare `pulumi stack
# output`. Wrapped here, it is encrypted at rest and shown only on request:
#
#   pulumi stack output env_smtp --show-secrets
pulumi.export(
    "env_backup",
    pulumi.Output.secret(
        pulumi.Output.all(
            bucket.name, bucket_key.access_key_id, bucket_key.secret_access_key
        ).apply(
            lambda a: "\n".join(
                [
                    f"BACKUP_BUCKET={a[0]}",
                    f"AWS_ACCESS_KEY_ID={a[1]}",
                    f"AWS_SECRET_ACCESS_KEY={a[2]}",
                    "AWS_DEFAULT_REGION=ca-central-1",
                ]
            )
        )
    ),
)

pulumi.export(
    "env_smtp",
    pulumi.Output.secret(
        pulumi.Output.all(mail_key.id, mail_key.ses_smtp_password_v4).apply(
            lambda a: "\n".join(
                [
                    "SMTP_HOST=email-smtp.ca-central-1.amazonaws.com",
                    "SMTP_PORT=587",
                    f"SMTP_USER={a[0]}",
                    f"SMTP_PASSWORD={a[1]}",
                    "SMTP_STARTTLS=true",
                ]
            )
        )
    ),
)

# The seven records to enter at GoDaddy. Printed rather than applied, and
# printed as a block you can read top to bottom, because two of them have traps:
#
#   * SPF must be ONE record naming BOTH senders. SES sends the offers; GoDaddy
#     sends whatever you type by hand from the info@ mailbox. Two SPF TXT
#     records on one name is a permanent failure, not a merge -- if GoDaddy has
#     already created one, EDIT it.
#   * DMARC starts at p=none on purpose, so a misconfiguration arrives as a
#     report instead of silently binning your mail. Tighten it after a few
#     clean weeks.
pulumi.export(
    "dns_records",
    pulumi.Output.all(
        static_ip.ip_address, email_identity.dkim_signing_attributes
    ).apply(
        lambda a: "\n".join(
            f"{kind:<6} {name:<42} {value}"
            for kind, name, value in (
                [
                    ("A", "@", a[0]),
                    ("A", "www", a[0]),
                ]
                + [
                    (
                        "CNAME",
                        f"{token}._domainkey",
                        f"{token}.dkim.amazonses.com",
                    )
                    for token in (
                        a[1].get("tokens")
                        or ["<pending: re-run `pulumi up` once SES has issued them>"]
                    )
                ]
                + [
                    (
                        "TXT",
                        "@",
                        "v=spf1 include:amazonses.com "
                        "include:secureserver.net -all",
                    ),
                    (
                        "TXT",
                        "_dmarc",
                        f"v=DMARC1; p=none; rua=mailto:info@{DOMAIN}",
                    ),
                ]
            )
        )
    ),
)
