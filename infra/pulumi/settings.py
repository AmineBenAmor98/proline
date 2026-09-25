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

# Per machine, so set it once on yours:
#
#   pulumi config set sshPublicKey "$(cat ~/.ssh/id_ed25519.pub)"
#
# Your own public key is uploaded rather than letting Lightsail generate the pair,
# which would leave a private key in this stack's state. It is safe in git, in a
# public repository: a public key's only power is authorising the private half.
SSH_PUBLIC_KEY = _config.require("sshPublicKey")

# Who may reach port 22. `0.0.0.0/0` in this stack -- see the long note in
# compute.py for why a /32 was tried and abandoned, and what it assumes about
# sshd. Required rather than defaulted precisely because it is a security
# decision: it should be a line someone chose, visible in the stack file.
SSH_CIDR = _config.require("sshCidr")

# The mailbox clients reply to, and the address SES is allowed to send as. One
# constant because the IAM policy condition and MAIL_REPLY_TO must agree.
MAIL_FROM_ADDRESS = f"contact@{DOMAIN}"

SMTP_HOST = f"email-smtp.{REGION}.amazonaws.com"
SMTP_PORT = 587

TAGS = {"Project": "proline", "ManagedBy": "pulumi"}
