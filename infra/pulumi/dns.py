"""The records to enter at GoDaddy.

Printed rather than applied: the domain is registered at GoDaddy, and the
community providers for it are a dependency this project does not need for a
handful of records typed once.

Deliberately free of any pulumi import, so it can be checked with plain values.

WHY THIS IS SPLIT IN TWO. The A and CNAME records can be stated outright: this
stack owns them and nothing else in the zone wants those names. SPF and DMARC
cannot, because a live domain usually already has them and there may be only ONE
of each. Printing a ready-made value for those invites pasting a second record
beside the first, which for SPF is a permanent authentication failure and for
DMARC can silently weaken a policy someone already set. So they are printed as
instructions about the existing record, not as a row to copy.
"""

# PEP 563: annotations stay strings, so `list[str] | None` and friends do not
# need Python 3.10 at runtime -- whatever python3 built the venv will do.
from __future__ import annotations

SES_SPF_INCLUDE = "amazonses.com"


def records(*, domain: str, ip: str, dkim_tokens: list[str] | None) -> str:
    """Format the record set, and the two judgement calls, as one readable block.

    The columns are headed TYPE / NAME / VALUE because those are the three fields
    GoDaddy's form asks for, in that order. Leave its TTL at the default.

    Read this with `pulumi stack output dns_records`. The summary that `pulumi up`
    prints at the end of an update truncates long strings with `...` and escapes
    the newlines, so records read off THAT are silently incomplete.
    """
    rows = [
        ("A", "@", ip),
        # `www` is a CNAME, NOT a second A record, and that is not a style choice:
        # a name may hold a CNAME or other records, never both (RFC 1034). GoDaddy
        # already ships `www` as a CNAME to the apex, so adding `A www` would mean
        # deleting that first -- and its UI will refuse the pair anyway.
        #
        # Pointing it at the apex is also the shape you want: the IP then lives in
        # exactly ONE record, so the rebuild that changes it (Lightsail cannot
        # resize in place) is a one-line DNS edit rather than two that can
        # disagree. `@` is GoDaddy's spelling for the apex; a provider that wants
        # an FQDN takes the domain with a trailing dot.
        ("CNAME", "www", "@"),
    ]
    if dkim_tokens:
        rows += [
            ("CNAME", f"{token}._domainkey", f"{token}.dkim.amazonses.com")
            for token in dkim_tokens
        ]

    # Widths measured from the content, not guessed. A DKIM name is a 32-character
    # token plus `._domainkey` = 43, which overflowed an earlier fixed 42 and left
    # name and value touching -- unreadable in the one place where a single
    # mistyped character means mail silently fails authentication.
    name_width = max(len(name) for _, name, _ in rows)
    lines = [
        "SET THESE EXACTLY. Edit the record if the name already exists; do not add",
        "a second one beside it.",
        "",
        f"{'TYPE':<6} {'NAME':<{name_width}} VALUE",
        f"{'-' * 6} {'-' * name_width} {'-' * 5}",
    ]
    lines += [f"{kind:<6} {name:<{name_width}} {value}" for kind, name, value in rows]

    if not dkim_tokens:
        lines += [
            "",
            "The 3 DKIM CNAME records are missing above because SES had not issued",
            "the tokens when this ran. Re-run `pulumi up` and read this again.",
        ]

    lines += [
        "",
        "",
        "THEN TWO THAT DEPEND ON WHAT IS ALREADY IN THE ZONE",
        "===================================================",
        "",
        "SPF -- a TXT record on `@`.",
        "",
        "  There may be only ONE `v=spf1` record on a name. A second is a permanent",
        f"  failure, not a merge. So find the existing one and add `include:{SES_SPF_INCLUDE}`",
        "  to it, in front of the closing `-all`. Do not paste a whole new record.",
        "",
        f"    ...existing mechanisms... include:{SES_SPF_INCLUDE} -all",
        "",
        f"  Only if the zone has no v=spf1 record at all:  v=spf1 include:{SES_SPF_INCLUDE} -all",
        "",
        "  SPF also allows at most 10 DNS-querying mechanisms across the whole",
        f"  chain, counting nested includes. `{SES_SPF_INCLUDE}` is flat and costs 1.",
        "  Exceeding 10 is a permerror that fails every sender at once, so count",
        "  before adding to a record that already has several includes.",
        "",
        "DMARC -- a TXT record on `_dmarc`.",
        "",
        "  If one already exists, LEAVE IT ALONE. A policy someone already set is",
        "  worth more than anything this file can guess, and replacing a stricter",
        "  one with a weaker one is a regression that nothing will warn you about.",
        "",
        f"  Only if there is none:  v=DMARC1; p=none; rua=mailto:contact@{domain}",
        "",
        "  Start at p=none so a misconfiguration arrives as a report rather than",
        "  silently binning your mail; tighten after a few clean weeks.",
        "",
        "  WHICHEVER POLICY IS IN FORCE, DKIM IS WHAT CARRIES OFFER MAIL THROUGH IT.",
        "  SES's default Return-Path is on amazonses.com, so SPF authenticates but",
        "  does not ALIGN with the From domain -- and DMARC needs alignment, not",
        "  merely a pass. That leaves DKIM as the only thing that can satisfy it.",
        "  Under `p=quarantine` or stricter, offer mail sent before SES reports the",
        "  identity as Verified goes to junk. Check that first, every time.",
    ]

    return "\n".join(lines)
