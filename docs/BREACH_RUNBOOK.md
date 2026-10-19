# Personal data breach runbook

What to do if personal data in this app may have been seen, changed, lost or taken by someone who should not have
it. This is a plain-language draft written for this app and its server. It is **not legal advice**. Check it
against the Digital Personal Data Protection Act, 2023 and the DPDP Rules (2025), and update it when they change.

**In short:** contain it first, then tell the affected people and the Data Protection Board of India **without
delay**, and send the Board a detailed report **within 72 hours** of becoming aware of the breach.

Keep a running log from the first minute: time, what you saw, what you did. Use UTC or IST throughout, not a mix.

## 1. Detect: signs that something is wrong

- **Admin → Activity** shows sign-ins, invites or account changes you did not expect (for example an invite you
  did not create, or a sign-in for an account at an odd time).
- An invited person reports records or files they did not add, or missing ones.
- The server shows unknown processes, users, SSH keys, cron jobs or unexpected outgoing traffic. The disk suddenly
  fills up or files change that should not.
- Backups fail, or the backup bucket shows objects or deletions you did not make (Oracle audit logs).
- A device or computer with an open session, the restic password, `.env` or a downloaded backup is lost or stolen.
- Someone tells you (a user, Google, Oracle or a security researcher).

## 2. Contain: stop it getting worse (first hour)

Do what fits. When in doubt, contain more rather than less.

1. **Take the app offline** if the server itself may be compromised: `sudo systemctl stop medical-records` (or stop
   the container). Leave the VM running so evidence is kept.
2. **Disable affected accounts:** Admin → Accounts → Disable. This signs them out at once.
3. **Sign everyone out and void all invite links:** change `SESSION_SECRET` in the app's environment and restart.
   Every session and every pending invite link stops working.
4. **Rotate secrets** that may have leaked:
   - Google OAuth client secret (Google Cloud console → Credentials), then update `GOOGLE_CLIENT_SECRET`.
   - Oracle Customer Secret Keys for `backup-writer` and `backup-reader` (delete the old ones, make new ones).
   - The restic password, if it may be known: `restic key add`, then `restic key remove <old id>`. Update the
     password file on the VM and in your password manager.
   - SSH keys for the VM, and the Oracle console password and 2-factor if the account may be affected.
5. **Keep evidence:** before changing the server further, take a block volume backup in the Oracle console, and
   copy the app's logs and `journalctl` output somewhere safe.

## 3. Assess: what happened and to whom (first day)

Write down, as best you can:

- What happened, how, and when it started and was found.
- Which accounts are affected (Admin → Accounts and Activity help) and what kind of data: health records,
  attached files, names and emails.
- Whether data was only seen, or also changed, deleted or copied out.
- What you have done to contain it, and what risk remains for the people affected.

If you cannot tell which accounts were affected, treat all of them as affected.

## 4. Notify (without delay; detailed report within 72 hours)

### The people affected

Tell each affected person, in plain language, through their email:

- what happened and when, as far as you know;
- what data of theirs is involved;
- what the likely consequences are for them;
- what you have done and are doing about it;
- what they can do to protect themselves (for example: be careful with messages that mention their health,
  sign out of all devices, download their data);
- who to contact: the grievance contact shown in the app.

Template:

> Subject: Important: a security problem with your medical records app
>
> On [date] we found that [what happened]. This may have affected your [records / attached files / name and
> email] stored in the app. [What we know about whether it was seen, changed or copied.]
>
> We have [what was done: for example taken the app offline, signed everyone out, changed passwords and keys].
> [What we are still doing.]
>
> What you can do: [steps]. If you have questions, reply to this email or contact [grievance name, email].
>
> We are sorry. We have also reported this to the Data Protection Board of India.

### The Data Protection Board of India

- **Without delay:** an initial report with what you know so far (nature, extent, timing and location of the
  breach, and its likely impact).
- **Within 72 hours** of becoming aware (or longer if the Board allows): a detailed report with the facts and
  circumstances, the cause, what was done to reduce the risk, findings about who caused it if known, what you have
  changed so it does not happen again, and a report on the notices sent to the affected people.

Use the Board's official reporting channel as published at the time. Check the Board's website for the current
form and address, because these may change.

## 5. Recover and learn

- Fix the cause before going back online. If the server may have been taken over, build a new VM and restore
  from a backup made **before** the breach (`DEPLOY.md` section 6), rather than cleaning the old one.
- Watch Admin → Activity and the server closely for a few weeks.
- Write a short record: timeline, cause, impact, notices sent (to whom and when), and what changed. Keep it with
  your records for at least as long as the law requires (at least one year).
- Update this runbook with anything that was missing.

## Contacts to have ready

| Who | How |
| --- | --- |
| Grievance contact shown in the app | `GRIEVANCE_NAME` / `GRIEVANCE_EMAIL` (default: the admin email) |
| Data Protection Board of India | Official website and reporting channel (check the current address) |
| Oracle Cloud support | Oracle Cloud console → Support |
| Google Cloud (OAuth client) | Google Cloud console → APIs & Services → Credentials |
| CERT-In (cyber security incidents in India) | incident@cert-in.org.in. Check whether the incident must also be reported to CERT-In (within 6 hours for listed incident types) |
