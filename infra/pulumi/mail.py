"""Sending as the domain: the SES identity, and a credential that can do nothing else."""

# PEP 563: annotations stay strings, so `list[str] | None` and friends do not
# need Python 3.10 at runtime -- whatever python3 built the venv will do.
from __future__ import annotations

import json
from typing import NamedTuple

import pulumi_aws as aws


class Sender(NamedTuple):
    identity: aws.sesv2.EmailIdentity
    access_key: aws.iam.AccessKey


def provision(*, domain: str, from_address: str, tags: dict) -> Sender:
    # Easy DKIM: AWS holds the private key and gives us three CNAMEs to publish.
    identity = aws.sesv2.EmailIdentity(
        "proline-domain",
        email_identity=domain,
        dkim_signing_attributes=aws.sesv2.EmailIdentityDkimSigningAttributesArgs(
            next_signing_key_length="RSA_2048_BIT"
        ),
        tags=tags,
    )

    # The app's mail credential. Send-only, and only as this address: if the SMTP
    # password leaks off the box, what it buys is the ability to send mail that
    # already looks like ours -- not to read SES, change identities, or touch
    # anything else in the account.
    user = aws.iam.User("proline-mailer", name="proline-mailer", tags=tags)

    aws.iam.UserPolicy(
        "proline-mailer-policy",
        user=user.name,
        # The FromAddress condition must match MAIL_FROM in /srv/proline/.env. It
        # compares the address only, so the display name in
        # `Proline Cleaning Solutions <contact@...>` is fine -- but if you ever
        # change the sending address and SES starts answering AccessDenied, this
        # is why.
        policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ses:SendRawEmail", "ses:SendEmail"],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {"ses:FromAddress": from_address}
                        },
                    }
                ],
            }
        ),
    )

    # `id` is the access key id, which is also the SMTP username;
    # `ses_smtp_password_v4` is the key's secret converted to an SMTP password.
    access_key = aws.iam.AccessKey("proline-mailer-key", user=user.name)

    return Sender(identity=identity, access_key=access_key)
