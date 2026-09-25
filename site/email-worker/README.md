# Mail for codecartographer.dev

Two mailboxes, one inbox. Cloudflare Email Routing receives mail for the domain, this worker tags each message by the mailbox it was sent to and forwards it, and a filter in your inbox turns the tag into a label.

| Address | Mailbox tag | Label |
|---|---|---|
| support@codecartographer.dev | `support` | Cartographer/Support |
| mapit@codecartographer.dev | `feedback` | Cartographer/Feedback |

Anything sent to another name at the domain is rejected, unless `FALLBACK` is set, in which case it is forwarded with the tag `unknown`.

## Set up, once

1. **Verify the inbox.** Cloudflare → Email → Email Routing → Destination addresses → add the inbox that should receive everything. Click the link in the verification email.
2. **Deploy the worker.** In this folder:
   ```bash
   npm i -g wrangler && wrangler login
   wrangler deploy
   ```
   Then in the Cloudflare dashboard open the worker → Settings → Variables and set `DEST_SUPPORT`, `DEST_FEEDBACK` and `DEST_DEFAULT` to the verified inbox (or edit `wrangler.toml` first). If you want separate inboxes per mailbox, verify each one.
3. **Route the addresses to the worker.** Email Routing → Routing rules → Create address: `support` → Send to a Worker → `codecartographer-mail`. Repeat for `mapit`. Set the catch-all rule to "Send to a Worker" as well if you want the worker to handle (reject or fall back) unknown names.
4. **Send two test mails** from another account, one to each address. Both should arrive in the inbox with the original `To:` intact and the `X-Codecartographer-*` headers added.

## Labels

Forwarding keeps the original `To:` header, so the simplest labels need no header matching at all.

**Gmail:** Settings → Filters and Blocked Addresses → Create a new filter.

| Filter field | Value | Action |
|---|---|---|
| To | `support@codecartographer.dev` | Apply the label Cartographer/Support, never send to Spam |
| To | `mapit@codecartographer.dev` | Apply the label Cartographer/Feedback, never send to Spam |

Create the two labels first (Cartographer, with Support and Feedback nested under it) so the filter can pick them.

**Fastmail, Proton, Apple Mail rules:** match the header `X-Codecartographer-Mailbox` equal to `support` or `feedback`, or match the `To` address as above.

## Adding a mailbox

Add one line to `MAILBOXES` in `worker.js` (name, tag, label, and the variable that holds its destination), add the variable, redeploy, and add the routing rule for the new address. Plus-addressing works without changes: `support+launch@` is treated as `support`.

## What the worker does not do

It does not rewrite subjects (Email Routing cannot change the message body or subject) and it does not auto-reply. If you want an acknowledgement for feedback sent to mapit@, that is a small addition using `message.reply`, with loop guards for auto-generated mail; say so and it can be added.
