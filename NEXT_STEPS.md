# VANTAG — ALL REMAINING STEPS (ONE SHOT)

Read this file top to bottom. Execute each block. Paste results back in chat.

---

## BLOCK A — Test the webhook works (run in VPS terminal)

Paste this whole thing into the VPS SSH window:

```
cd /var/www/vantag
PAYLOAD='{"event":"payment.captured","payload":{}}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac 'Anandkr#01' | awk '{print $2}')
echo "Signature: $SIG"
curl -s -w "\nCODE=%{http_code}\n" -X POST https://retail-vantag.com/api/billing/webhook/sg -H "Content-Type: application/json" -H "X-Razorpay-Signature: $SIG" -d "$PAYLOAD"
```

EXPECTED RESULT:
- Line 1: `{"received":true,"event":"payment.captured"}`
- Line 2: `CODE=200`

If you see `CODE=200` → webhook is fully working. Done forever.
If you see `CODE=400` → paste output to me.

---

## BLOCK B — Confirm wrong signature is rejected (security test)

```
curl -s -w "\nCODE=%{http_code}\n" -X POST https://retail-vantag.com/api/billing/webhook/sg -H "Content-Type: application/json" -H "X-Razorpay-Signature: WRONG" -d '{"event":"test"}'
```

EXPECTED: `CODE=400` with `{"detail":"Invalid webhook signature"}`

---

## BLOCK C — Fix Razorpay webhook to 8 events (in browser, Razorpay dashboard)

Right now your webhook has only 3 events. It needs 8.

Steps:
1. Razorpay dashboard → Settings → Webhooks
2. Click the row `https://retail-vantag.com/api/billing/webhook/sg`
3. Click the blue "Edit" button (top right of the detail panel)
4. Scroll down to "Active Events"
5. Tick these 8 (leave everything else unticked):
   - payment.authorized
   - payment.captured
   - payment.failed
   - order.paid
   - subscription.activated
   - subscription.charged
   - subscription.cancelled
   - subscription.halted
6. Scroll down, click "Update Webhook"
7. Confirm the row now shows "8 events" in the list

---

## BLOCK D — Set up support@retail-vantag.com email (Hostinger web UI)

1. Log in to https://hpanel.hostinger.com
2. Left menu → Emails → find retail-vantag.com → Manage
3. Click "Create Email Account"
   - Email: support
   - Password: (strong, save it)
4. Accept MX record setup if prompted
5. Wait 5 minutes
6. Send test email from your Gmail to support@retail-vantag.com
7. Open https://mail.hostinger.com, log in with support@retail-vantag.com
8. Confirm test email arrived
9. Optional: Emails → Forwarders → forward support@ → your Gmail

---

## BLOCK E — End-to-end app test (browser)

Open https://retail-vantag.com and test each:

1. Landing page loads with HTTPS padlock, no cert error
2. Language switcher (top nav) changes language
3. Click Login, use demo@vantag.io / demo1234
4. Reach dashboard, no "Tenant not found" error
5. Top-right badge shows "Connected" not "Disconnected"
6. Sidebar → Billing/Subscription → click a plan → Razorpay checkout opens in SGD
7. Close checkout. Open chat/Help Center. Ask "what is vantag?" → GPT answers
8. Open Downloads page. Click Windows button → real .zip file downloads
9. Logout. Click Register. Use your real email. Get OTP email. Verify.

For each failure: screenshot + tell me which number failed.

---

## BLOCK F — Edge Agent test (on your Windows laptop)

1. Dashboard → Downloads → Windows button → downloads vantag-edge-agent-windows.zip
2. Extract zip
3. Double-click run.bat
4. Console shows "Scanning network... Found camera... Registered with cloud"
5. Refresh browser dashboard → camera appears as Online

If any step fails: screenshot + paste.

---

## BLOCK G — Still pending (NOT urgent, do when ready)

1. India Razorpay keys — paste rzp_live_in_... Key ID + Secret in chat, I wire it
2. India webhook — after IN keys added, URL will be https://retailnazar.in/api/billing/webhook/in, same secret Anandkr#01
3. Deep i18n pass — translate dashboard body into Hindi/Tamil/Telugu etc. Say "do i18n" when ready

---

## YOUR NEXT ACTIONS (IN ORDER)

1. Run BLOCK A → paste the CODE= line
2. Run BLOCK B → paste the CODE= line
3. Do BLOCK C in Razorpay UI → screenshot showing "8 events"
4. Do BLOCK D in Hostinger → tell me when email arrives
5. Do BLOCK E browser tests → screenshot failures only
6. Do BLOCK F Edge Agent → screenshot result

Paste everything in ONE reply. I will batch-fix whatever is broken.
