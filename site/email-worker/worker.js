/**
 * Cloudflare Email Worker for codecartographer.dev.
 *
 * Email Routing hands every message for the domain to this worker. The worker
 * reads the address the message was sent to, tags the message with headers
 * that name the mailbox, and forwards it to the inbox configured for that
 * mailbox. Anything sent to an address that is not a mailbox is rejected (or
 * forwarded to FALLBACK when that is set), so spam to random names never
 * reaches you.
 *
 * Labels in your inbox come from filters on the original "To" address, which
 * forwarding preserves; see README.md for the Gmail rules. The headers added
 * here are for mail clients that filter on headers and for your own audit.
 *
 * Settings live in wrangler.toml under [vars]; destinations must be verified
 * in Cloudflare → Email → Email Routing → Destination addresses first.
 */

// local part of the address -> mailbox. Add a line to add a mailbox.
const MAILBOXES = {
  support: { tag: "support", label: "Cartographer/Support", dest: "DEST_SUPPORT" },
  mapit:   { tag: "feedback", label: "Cartographer/Feedback", dest: "DEST_FEEDBACK" },
};

export default {
  async email(message, env, ctx) {
    const to = String(message.to || "").toLowerCase();
    const local = to.split("@")[0].split("+")[0]; // support+launch@ still counts as support
    const box = MAILBOXES[local];

    if (!box) {
      if (env.FALLBACK) {
        await message.forward(env.FALLBACK, tagHeaders("unknown", to, "Cartographer/Unsorted"));
        return;
      }
      message.setReject(`No such mailbox: ${to}`);
      return;
    }

    const destination = env[box.dest] || env.DEST_DEFAULT;
    if (!destination) {
      message.setReject("Mailbox is not configured yet");
      return;
    }
    await message.forward(destination, tagHeaders(box.tag, to, box.label));
  },
};

function tagHeaders(tag, to, label) {
  const h = new Headers();
  h.set("X-Codecartographer-Mailbox", tag);   // support | feedback | unknown
  h.set("X-Codecartographer-To", to);         // the address it was actually sent to
  h.set("X-Codecartographer-Label", label);   // the label a filter should apply
  return h;
}
