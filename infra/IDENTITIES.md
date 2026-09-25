# Who is who, and how mail actually flows

Seven different logins touch this system, and nothing about using it forces you to
notice they are different. They have different owners, different blast radii, and
live in different places. Getting them confused is how someone ends up putting an
admin key on a web server.

Read this before changing any credential, and before changing `MAIL_FROM`.

---

## 1. The seven identities

| Who | What it is | Where the secret lives | What it can do |
|---|---|---|---|
| **AWS root** | the AWS account itself | nowhere — no access keys, MFA only | everything, including closing the account. Billing and MFA only, never daily work |
| **Your IAM admin** | an IAM user for you | `~/.aws/credentials`, profile `proline`, on your laptop | everything in AWS. This is what `pulumi` runs as |
| **`proline-mailer`** | IAM user created by `mail.py` | `SMTP_USER` / `SMTP_PASSWORD` in `/srv/proline/.env` | **send email, only as `contact@`. Nothing else, anywhere** |
| **`ubuntu`** | the Linux account on the instance | your SSH private key, `~/.ssh/id_ed25519` | full control of the box via `sudo` |
| **`proline`** (Postgres) | the database role | `/srv/proline/db_password`, and inside `DATABASE_URL` | read/write that one database. Not reachable from the internet at all |
| **`ADMIN_USERNAME`** | the website's own admin login | `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `/srv/proline/.env` | view and manage leads at `/admin`. No relation to AWS or Linux |
| **`contact@proline-…`** | a Microsoft 365 mailbox | your Microsoft 365 password | send and receive human email |

Four separate things are called "the password" in conversation, so when something
is wrong, name which one: the database role, the website admin, the SMTP
credential, or the Microsoft 365 mailbox.

### The one that matters most: `proline-mailer`

The app needs to send mail, and the tempting shortcut is to hand it the admin key
already on your laptop. `mail.py` creates a separate IAM user whose entire policy
is *send email, and only from `contact@`*:

```json
"Action": ["ses:SendRawEmail", "ses:SendEmail"],
"Condition": { "StringEquals": { "ses:FromAddress": "contact@proline-cleaningsolutions.com" } }
```

Its access key **is** the SMTP username, and `ses_smtp_password_v4` is that key's
secret converted into an SMTP password. That matters because the file it sits in,
`/srv/proline/.env`, is on an internet-facing machine. If it leaks, the attacker
gains the ability to send mail that looks like yours — bad, and recoverable by
deleting one key. They cannot read your SES, list your instances, see your bill,
or touch anything else in the account.

**`ses:FromAddress` must match `MAIL_FROM`.** It compares the address only, so the
display name in `Proline Cleaning Solutions <contact@…>` is fine. If you ever
change the sending address and SES starts answering `AccessDenied`, this condition
is why — the policy is in `mail.py`, not in the console.

---

## 2. Two mail systems, one domain

This is the thing that confuses everyone, including whoever set it up:

> **Amazon SES only sends. Microsoft 365 only receives.**

They are completely independent. Neither knows the other exists.

- **Outbound, automatic**: quote emails, sent by the app through SES.
- **Inbound, human**: client replies, delivered by Microsoft 365 to your Outlook.

They share exactly two DNS records — **SPF** and **DMARC** — and those are the
only records in the zone where an edit can break the other system. That is why
`infra/DNS.md` singles them out. Everything else in the zone belongs to precisely
one owner.

A useful consequence: you cannot "reply from the app", and the app cannot read
mail. If you need to see what a client said, that is Outlook, not `/admin`.

---

## 3. What happens when someone asks for a quote

1. A customer fills in the form. The app prices it from the active rate card.
2. The app opens SMTP to `email-smtp.ca-central-1.amazonaws.com:587` and
   authenticates as **`proline-mailer`**.
3. SES asks two questions:
   - *May this user send as `contact@`?* — the IAM condition above says yes, that
     address and no other.
   - *Is this domain verified?* — yes, and the three DKIM `CNAME`s in your DNS are
     what prove it.
4. SES signs the message with DKIM and delivers it.
5. The customer's mail provider checks that signature against your DNS. It
   matches, so the mail is authenticated and lands in the inbox rather than junk.
6. The customer clicks **Reply**. That goes to `MAIL_REPLY_TO` → `contact@` →
   **Microsoft 365** → your Outlook.
7. Separately, a notification goes to `NOTIFY_EMAIL_TO` so somebody knows a lead
   arrived without watching `/admin`.

**Step 5 is the fragile one, and it fails silently.** DMARC on this domain is
`p=quarantine`, and DKIM is the only thing that can satisfy it — SES's default
Return-Path is on `amazonses.com`, so SPF passes but does not *align* with the
From domain, and DMARC requires alignment rather than a mere pass. So if the DKIM
records are wrong, or SES has not yet reported the identity as **Verified**, quote
emails go to junk with nothing in the application logs to show for it. Section 5
of `infra/DNS.md` has the detail. Confirm **Verified** in the SES console before
any real send.

---

## 4. The three addresses in `/srv/proline/.env`

| Setting | Value | Why |
|---|---|---|
| `MAIL_FROM` | `Proline Cleaning Solutions <contact@…>` | Who the mail appears to be from. **Must** be `contact@` — the IAM policy permits no other address |
| `MAIL_REPLY_TO` | `contact@…` | Where replies land: the Microsoft 365 mailbox a human reads |
| `NOTIFY_EMAIL_TO` | `contact@…` | Where the "new lead" alert goes |

All three are the company mailbox, deliberately.

A lead notification is **company correspondence, not personal mail.** Pointing it
at whoever happened to deploy the site means it breaks when that person changes
address, loses their phone, or stops being involved — and it scatters one enquiry
across two mailboxes, the alert in a personal inbox and the client's reply in the
company one. One address keeps the whole thread together and keeps working when
the staff change.

It is also the pragmatic choice while SES is in the **sandbox**: sandbox mode only
delivers to verified addresses, and the entire domain is already a verified
identity — so `contact@` works today, where a personal Gmail address would have to
be verified separately first.

If you later want alerts somewhere else as well, add a forwarding rule in
Microsoft 365 rather than changing `NOTIFY_EMAIL_TO`. Then the record still lives
in the company mailbox and the copy is a convenience on top.

---

## 5. Where every secret physically is

| Secret | Lives in | Also in |
|---|---|---|
| AWS admin access key | `~/.aws/credentials` on your laptop | — |
| Pulumi passphrase | `PULUMI_CONFIG_PASSPHRASE_FILE`, `chmod 600` | — |
| SES SMTP password | `/srv/proline/.env` on the box | Pulumi stack state, encrypted (`pulumi stack output env_smtp --show-secrets`) |
| Database password | `/srv/proline/db_password` | `DATABASE_URL` in `/srv/proline/.env` — the same value twice, by necessity |
| Website admin password | `/srv/proline/.env` | — |
| Microsoft 365 password | your password manager | — |
| SSH private key | `~/.ssh/id_ed25519` on your laptop | — |

**Nothing in this table is in git**, and nothing is in Pulumi's `user_data` —
user data is readable from the instance metadata endpoint by anything running on
the box, and stored in plain text in the stack. That is why `/srv/proline/.env`
is written by hand over SSH rather than generated by `user-data.sh`.

Two footguns in that table:

- **The database password appears twice** — in `db_password` (which Postgres
  reads) and inside `DATABASE_URL` (which the app reads). They must match.
  Changing one and not the other locks the app out of its own data.
- **Generate it with `openssl rand -hex`, never `-base64`.** Base64 contains `+`
  and `/`, and roughly 74% of 32-byte base64 strings contain at least one. A `/`
  in the password terminates the URL's authority section, so
  `postgresql+asyncpg://proline:ab/cd@db:5432/proline` parses with **`proline` as
  the hostname** — and the resulting error mentions neither the password nor the
  URL.

---

## 6. If something is wrong, check the right identity

| Symptom | The identity at fault |
|---|---|
| `pulumi` says "No valid credential sources found" | your IAM admin — `export AWS_PROFILE=proline` |
| SES returns `AccessDenied` on send | `proline-mailer` — `MAIL_FROM` no longer matches the IAM condition |
| Quote emails arrive in junk | not a credential. DKIM/DMARC — see `infra/DNS.md` §5 |
| Quote emails vanish with no error | SES sandbox — the recipient is not a verified address |
| Can't log in at `/admin` | `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `/srv/proline/.env` |
| App can't reach the database | the `proline` Postgres role — `DATABASE_URL` and `db_password` disagree |
| `ssh` hangs at "Connecting to" | not a credential. The Lightsail firewall — `sshCidr` in `compute.py` |
| `ssh` says `Permission denied (publickey)` on a new box | not a credential either. `cloud-init` has not written `authorized_keys` yet — wait two minutes |
| Client replies bounce | the Microsoft 365 mailbox — `contact@` does not exist in the tenant |

The last four are the ones that waste an afternoon, because none of them are
credential problems and all of them look like one.
