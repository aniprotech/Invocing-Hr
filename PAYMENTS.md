# Payments: GoCardless

Tenants top up their wallet by bank debit through GoCardless. That is the only
way money comes in.

```
GOCARDLESS_ACCESS_TOKEN=...
GOCARDLESS_WEBHOOK_SECRET=...
GOCARDLESS_ENVIRONMENT=sandbox      # sandbox until you mean it; live charges real accounts
```

Webhook endpoint to register in the GoCardless dashboard:

```
POST https://your-host/api/wallet/webhook/gocardless
```

Without `GOCARDLESS_WEBHOOK_SECRET` the endpoint refuses everything with a 503.
An unverified webhook is worse than none — anyone who found the URL could
credit their own wallet.

## The thing to understand: this is not a card

A card authorises in seconds and either works or does not. Bank debit does not.
The flow is *authorise once, collect repeatedly*, and a collection that has
been **submitted** can still **fail days later** for want of funds.

That single fact drives the whole design:

**Credit is added when GoCardless says `confirmed`, never on `submitted`.**

Crediting earlier would hand a tenant balance that had not arrived — they would
spend it on AI calls, and the debit would bounce three days later leaving the
wallet negative and the money gone. So there is exactly one place that adds
credit (`credit_topup_once`, called from the webhook), guarded by a `credited`
flag so a retried webhook cannot pay twice.

### What a tenant experiences

- **Instant Bank Pay** (open banking, where their bank supports it): confirmed
  in seconds. Balance appears almost immediately.
- **Ordinary Direct Debit**: a few working days. Balance appears when it clears.

The app says this before they commit and again when they return, because
"payment complete" would be a lie on the slower path. If most of your tenants
are on the slow path and need credit immediately, that is a **product decision
about who carries the risk** — the code will not make it for you.

## Automatic top-up

The same authorisation leaves a reusable mandate behind, which is what lets a
wallet top itself up when it falls below its owner's threshold.

The nightly job **asks for money and stops**. It credits nothing. The webhook
credits when the bank confirms, exactly as for a manual top-up — one money
path, one place that adds balance.

Two guards, because collecting twice from someone's bank account is not a
small mistake:

1. A `DBAutoCharge` row keyed `topup:{client}:{date}` is written **before**
   GoCardless is called, so a wallet still under its threshold is not collected
   from on every run.
2. That same key is sent as GoCardless's `Idempotency-Key`, so even a retry
   that got past the first guard is deduped on their side.

## Currencies

Bank debit runs on schemes, and a currency without one cannot be collected:
**GBP** (Bacs), **EUR** (SEPA), **USD** (ACH), **AUD** (BECS), **NZD**, **CAD**,
**SEK**, **DKK**.

A wallet set to anything else — INR, for instance — cannot be topped up at all,
and the top-up screen says so rather than failing at the gateway.

## The old gateways

Stripe, Razorpay and PayPal are still in the code and still have working
webhooks, because orders already taken through them have to settle and
reconcile. Nothing offers them any more and `/api/wallet/topup` refuses them.

One consequence worth knowing: a tenant holding an **old card mandate** for
automatic top-up cannot be collected from. The job logs a warning and counts it
as failed rather than skipping silently — those tenants need to authorise again
through GoCardless.
