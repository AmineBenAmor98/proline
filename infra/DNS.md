# DNS for proline-cleaningsolutions.com

Every record in the zone, what it does, and what breaks without it. Captured
25 Sep 2026 from the live zone, not from memory.

Nameservers are `ns31` / `ns32.domaincontrol.com`, so **GoDaddy is where you edit
these**. Nothing in this repo applies them — `infra/pulumi/dns.py` only prints
what the AWS side needs, and you type it in.

**Two independent mail systems share this domain.** Microsoft 365 handles your
mailboxes, Amazon SES sends the automated quote emails. They coexist fine, but
they share two records — SPF and DMARC — and those are the only ones where an
edit can break the other system. Everything else belongs to exactly one owner.

---

## 1. The website — owned by this project

| Type | Name | Value |
|---|---|---|
| A | `@` | `16.54.157.79` |
| CNAME | `www` | `@` |

The A record is the Lightsail static IP. `www` is a CNAME to the apex rather than
a second A record, so the IP appears exactly once: when the instance is rebuilt
(Lightsail cannot resize in place, so this will happen) it is a one-line change.

A name may hold a CNAME **or** other record types, never both — so there is no
`A www`, and GoDaddy will refuse if you try to create one.

**If wrong:** the site is unreachable, and the TLS certificate cannot be issued
or renewed. The certificate covers both the apex and `www`, and Let's Encrypt
validates each name separately over HTTP — so both must resolve to this box, or
neither name gets a certificate.

---

## 2. Sending quote emails — Amazon SES, owned by this project

| Type | Name | Value |
|---|---|---|
| CNAME | `5y56vd3igleq4nv5oz4ntujtq5tpemgk._domainkey` | `5y56vd3igleq4nv5oz4ntujtq5tpemgk.dkim.amazonses.com` |
| CNAME | `k3slped64nlagpf5kzfig7yncuejw6ut._domainkey` | `k3slped64nlagpf5kzfig7yncuejw6ut.dkim.amazonses.com` |
| CNAME | `qgpjgqjxvjf3tg3t6wm4m72ewmj7elqf._domainkey` | `qgpjgqjxvjf3tg3t6wm4m72ewmj7elqf.dkim.amazonses.com` |

SES Easy DKIM. Three because SES rotates between them; **all three must resolve**
or the identity never reaches Verified. They are published by Pulumi as
`dns_records` and re-issued if the SES identity is ever destroyed and recreated.

SES also needs `include:amazonses.com` in the SPF record — see section 5.

**If wrong:** quote emails fail DKIM. Because DMARC here is at `p=quarantine`,
that means they land in junk. See the alignment note in section 5 — this is the
single most important thing on this page.

---

## 3. Receiving email — Microsoft 365, pre-existing, do not touch

| Type | Name | Value | Purpose |
|---|---|---|---|
| MX | `@` | `prolinecleaningsolutions-com01i.mail.protection.outlook.com` (priority 0) | Where mail to `@proline-cleaningsolutions.com` is delivered |
| TXT | `@` | `MS=ms57501288` | Proves domain ownership to Microsoft |
| TXT | `@` | `NETORGFT21161106.onmicrosoft.com` | Links the domain to your M365 tenant |
| CNAME | `autodiscover` | `autodiscover.outlook.com` | Lets Outlook configure itself from just an address |
| CNAME | `selector1._domainkey` | `selector1-…dkim.mail.microsoft` | M365's own DKIM |
| CNAME | `selector2._domainkey` | `selector2-…dkim.mail.microsoft` | M365's own DKIM |

Microsoft's DKIM uses selector names (`selector1`, `selector2`), SES uses random
tokens, so the two DKIM setups never collide.

**This is why you do not need a GoDaddy email plan** — you already have mailboxes
here. `contact@proline-cleaningsolutions.com` either exists already or is created
in the Microsoft 365 admin centre, not bought from GoDaddy.

**If wrong:** you stop receiving email. Since `MAIL_REPLY_TO` points at
`contact@`, client replies to quotes would bounce.

---

## 4. Teams / Skype for Business — pre-existing, do not touch

| Type | Name | Value |
|---|---|---|
| CNAME | `sip` | `sipdir.online.lync.com` |
| CNAME | `lyncdiscover` | `webdir.online.lync.com` |
| SRV | `_sip._tls` | `100 1 443 sipdir.online.lync.com` |
| SRV | `_sipfederationtls._tcp` | `100 1 5061 sipfed.online.lync.com` |

Client discovery for Teams. Unrelated to the website or to quote emails.

Also present and harmless: `CNAME msoid → clientconfig.microsoftonline-p.net`,
`CNAME email → email.secureserver.net` (GoDaddy webmail shortcut), and
`CNAME _domainconnect → _domainconnect.gd.domaincontrol.com` (GoDaddy's
one-click DNS setup hook).

---

## 5. The two shared records — the only dangerous ones

### SPF — one TXT record on `@`

```
v=spf1 include:amazonses.com include:secureserver.net -all
```

**There may be only ONE `v=spf1` record on a name.** A second is not merged with
the first — it is a permanent error that fails *every* sender at once. So this
record is always edited, never added.

Both mail systems live in this one line:

- `include:amazonses.com` — authorises SES to send as this domain. Flat, 1 lookup.
- `include:secureserver.net` — authorises Microsoft 365. It chains:
  `secureserver.net` → `spf-0.secureserver.net` → `spf.protection.outlook.com`.
  **Do not remove it thinking it is legacy GoDaddy** — it is what covers Outlook.
- `-all` — anything else claiming to be us should be rejected.

SPF permits at most **10 DNS-querying mechanisms** across the whole nested chain.
This record uses 4 (amazonses, secureserver, spf-0, outlook). Count before adding
another sender; crossing 10 is a permerror that breaks all mail.

### DMARC — one TXT record on `_dmarc`

```
v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;
```

Pre-existing and already strict. **Leave it as it is.** `p=quarantine` means mail
that fails authentication goes to junk rather than being delivered.

**The alignment trap, which decides whether quote emails land:**

DMARC does not ask "did SPF pass". It asks "did SPF or DKIM pass *and* match the
From domain". SES sends with a Return-Path on `amazonses.com`, so SPF passes but
does **not** align with `proline-cleaningsolutions.com`.

So for quote emails, **DKIM is the only thing that can satisfy DMARC.** Under
`p=quarantine`, a quote sent before SES reports the identity Verified goes to
junk, with nothing in the application logs to show for it.

Always confirm the SES identity shows **Verified** before a real send.

If you ever want SPF to align too, SES supports a custom MAIL FROM domain
(e.g. `mail.proline-cleaningsolutions.com`), which needs one extra MX and one
extra TXT. Not required — belt and braces.

---

## Checking it

```sh
D=proline-cleaningsolutions.com
dig +short A $D                      # 16.54.157.79
dig +short www.$D                    # 16.54.157.79
dig +short TXT $D | grep spf1        # must be exactly one line
dig +short TXT _dmarc.$D
dig +short MX $D
for t in 5y56vd3igleq4nv5oz4ntujtq5tpemgk \
         k3slped64nlagpf5kzfig7yncuejw6ut \
         qgpjgqjxvjf3tg3t6wm4m72ewmj7elqf; do
  dig +short CNAME $t._domainkey.$D
done                                 # three lines, all *.dkim.amazonses.com
```

Changes take up to the TTL to appear — 1 hour on most of these records.
