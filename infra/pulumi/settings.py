"""Every value this stack reads, in one place.

No defaults live here. A default in code beside a value in Pulumi.<stack>.yaml is
two sources of truth for one setting, and the one you edited is not always the
one that won. `require` makes a missing value fail immediately, naming itself.
"""

# PEP 563: annotations stay strings, so `list[str] | None` and friends do not
# need Python 3.10 at runtime -- whatever python3 built the venv will do.
from __future__ import annotations

import pulumi

_config = pulumi.Config()

# The region comes from the aws provider's own namespace rather than being
# repeated here, so the SMTP endpoint below cannot drift away from where the
# instance actually is.
REGION = pulumi.Config("aws").require("region")

DOMAIN = _config.require("domain")
AVAILABILITY_ZONE = _config.require("availabilityZone")
INSTANCE_BUNDLE = _config.require("instanceBundle")

# Deliberately absent from the committed stack file -- per person, per location:
#
#   pulumi config set sshPublicKey "$(cat ~/.ssh/id_ed25519.pub)"
#   pulumi config set adminSshCidr "$(curl -s https://checkip.amazonaws.com)/32"
#
# Your own public key is uploaded rather than letting Lightsail generate the
# pair, which would leave a private key in this stack's state. And 0.0.0.0/0 is a
# defensible answer on a dynamic address -- but it should be one you chose.
SSH_PUBLIC_KEY = _config.require("sshPublicKey")
ADMIN_SSH_CIDR = _config.require("adminSshCidr")

# The mailbox clients reply to, and the address SES is allowed to send as. One
# constant because the IAM policy condition and MAIL_REPLY_TO must agree.
MAIL_FROM_ADDRESS = f"contact@{DOMAIN}"

SMTP_HOST = f"email-smtp.{REGION}.amazonaws.com"
SMTP_PORT = 587

TAGS = {"Project": "proline", "ManagedBy": "pulumi"}
