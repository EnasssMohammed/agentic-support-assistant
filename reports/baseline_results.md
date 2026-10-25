# Baseline Results (non-agentic, single LLM call)

## n1
**Q:** The router shows a red internet light and there's no connection, what do I do?

**Expected:** guide_restart (escalation required: False)

**Baseline answered:** Sorry you're having trouble. A solid red Internet light usually means the router can’t reach your ISP or there’s no WAN link. Try these steps:

1) Power cycle (often fixes many issues)
- If you have a separate modem/ONT:
  - Unplug the modem from power, wait 30–60 seconds.
  - Plug the modem back in and wait until it’s online (all lights stable).
  - Then plug in the router and wait for it to boot.
- If you only have a gateway device, just power it off, wait 60 seconds, and power it back on.

2) Check cables and connections
- Ensure the Ethernet cable from the modem/ONT to the router’s WAN/Internet port is firmly connected.
- Check that the coax/telephone/fiber line from the wall is securely connected to the modem/ONT if you’re using a separate device.

3) Verify the modem/ONT status
- If you have a separate modem, make sure it’s online (no red lights on the modem itself). If the modem shows a red or no-Internet state, contact your ISP.
- If you’re on fiber, ensure the ONT is powered and showing a link (consult ISP if needed).

4) Check for an outage or account issue
- See if your ISP has an outage in your area (their status page or support line).
- If your service requires PPPoE/credentials, verify they’re entered correctly in the router (username/password may need updating after an outage or plan change).

5) Test with a wired connection
- Connect a computer directly to the modem (or ONT) with an Ethernet cable. Do you get Internet there? If yes, the issue is with the router; if no, the issue is with the modem/ISP.

6) Reset as a last resort
- If you don’t mind reconfiguring, you can reset the router to factory defaults (often a small recessed button; press 10–15 seconds).
- After reset, re‑enter your Internet settings (WAN type, PPPoE credentials if needed, Wi‑Fi name/password).

7) If you want model-specific help
- Tell me your router model and whether you have a separate modem/ONT (and your ISP type: cable, DSL, fiber). I can give you precise steps and any default login info.

If you’d like, I can guide you through these steps in detail once you share your model and setup. If the issue persists after these steps, you may need to contact your ISP or device support for a line reset or replacement.

---

## n2
**Q:** Diagnostics came back as a Hard Fault on my router.

**Expected:** escalate_immediately (escalation required: True)

**Baseline answered:** Sorry to hear that. A “Hard Fault” in router diagnostics usually points to a hardware issue (CPU, memory, flash, or power) rather than a simple software problem. Here are quick steps you can try to rule out common causes and decide if you can get it running again or need a replacement.

Immediate checks
- Power cycle: unplug the router, wait 30 seconds, plug back in. Let it fully reboot.
- Cooling and placement: make sure vents aren’t blocked and the unit isn’t overheating. Move it to a cooler, well-ventilated spot.
- Cables and power: use the official/stock power adapter and a good power outlet. If you have a known-good spare adapter that matches the spec, try it.
- Disconnect peripherals: unplug any USB drives, printers, or extra switches attached to the router to rule out external hardware causing the fault.
- Firmware status: if you can access the UI, check if there’s a firmware update and apply it. If the UI is inaccessible due to the fault, this step might need to be done via recovery/flash later.

Factory reset and recovery (if you can access the UI or recovery mode)
- Factory reset: if you’re able to reach the management page, perform a factory reset (note: this erases settings; you’ll need to reconfigure afterward). If you can’t access the UI, use the reset button on the back (hold for ~10–15 seconds) to restore to default.
- Firmware reflash: after resetting, reinstall the latest official firmware from the manufacturer’s site. If you can’t access the device, some models support a recovery/flash method via TFTP or a USB recovery file—follow the model-specific guide carefully.

If the problem persists
- It’s likely a hardware fault. If the device is under warranty or a service plan, this is a strong case for an RMA or replacement.
- Gather these details to speed up support:
  - Router model and serial number
  - Current firmware version (if accessible)
  - Exact wording of the diagnostic message or any LED indicators
  - Purchase date and place (for warranty)
  - Summary of steps you’ve already tried and whether the fault occurs on startup or after heavy use

Would you like me to help you with a model-specific plan (e.g., how to factory reset safely, how to flash firmware, or how to start an RMA)? If you share your router model and any exact diagnostic text or screenshots, I can tailor the steps and, if needed, guide you through the RMA process.

---

## n3
**Q:** I bought a digital license two days ago and want a refund.

**Expected:** deny_refund_digital_license (escalation required: False)

**Baseline answered:** I’m sorry to hear that. I can help you with a refund.

Refund eligibility for digital licenses depends on our policy (usually within 14 days of purchase and before the license has been activated). If the license has already been activated, refunds may not be available.

To proceed, please provide:
- Your order number or transaction ID
- The email used for the purchase
- The product name / license key
- Has the license been activated or redeemed? (Yes/No)
- Your reason for the refund

If you’d rather, you can also try to initiate the refund yourself in your account:
- Log in to your account
- Go to Purchases or Orders
- Find the digital license and select Request Refund (if the option is shown)

What to expect after we submit the refund:
- Refunds are issued to the original payment method and usually appear within 5–10 business days (timing can vary by payment provider).

If you share the details above, I can start the refund process for you right away.

---

## n4
**Q:** I've entered my password wrong 3 times and now I'm locked out.

**Expected:** trigger_password_reset (escalation required: False)

**Baseline answered:** Sorry you’re locked out—that’s rough. I can help you get back in. Here are the general steps, plus a couple of quick checks. If you tell me which service you’re trying to sign into, I can give exact instructions.

What you can do now
- On the sign-in page, look for a “Forgot password?” or “Need help signing in?” link and click it.
- Enter your username or email address associated with the account.
- Choose a way to verify your identity (usually via a code sent to your recovery email or phone, or answer security questions).
- Enter the verification code and reset your password. Create a new, strong password you don’t use elsewhere.
- Sign in with the new password and, if offered, enable two-factor authentication (2FA) for extra security.

If you’re seeing a lockout message
- Some services lock you temporarily after multiple failed attempts. If you see a timer (e.g., “Try again in 15 minutes”), wait the stated time and then try again with the correct credentials.
- Refrain from repeatedly trying passwords; it can extend the lockout.

If you can’t access recovery options
- Use the service’s official support contact or a dedicated account recovery form.
- You may be asked for identifying details (not your password). Have information like your account name, last login date, or last successful purchase handy.

Want me to tailor these steps to your exact service? Tell me which app or site you’re trying to sign into, and I’ll walk you through the precise reset flow.

---

## n5
**Q:** I bought a standard physical product 10 days ago. It stopped working, and I have the proof of purchase. Under the policy allowing standard products to be returned within 14 days, am I eligible to return it?

**Expected:** approve_return_within_window (escalation required: False)

**Baseline answered:** Yes. At 10 days since purchase, you’re within the 14-day window for standard product returns. Since it stopped working, you can typically choose a refund or a replacement under the return policy, and you may also have warranty options if applicable.

What to do next:
- Have your order number and proof of purchase ready.
- Start a return/exchange in your account (Orders > Return/Exchange) or tell me your order number and I can guide you through it.
- You’ll likely be issued an RMA and provided a shipping label. Please ship the item back in its original packaging with any accessories if possible.
- Tell us whether you want a refund to your original payment method or a replacement.

If you’d prefer, I can help initiate the process for you—just share your order number. And if the item is defective, we can also check for warranty options beyond the 14-day window.

---

## e1
**Q:** It's been going back and forth for a while and nothing's fixed, what now?

**Expected:** escalate_after_retry_limit (escalation required: True)

**Baseline answered:** I’m sorry this has been dragging on. I want to help get this fixed. To move things forward quickly, could you share a few details so I can escalate or create a higher-priority fix?

What I need (pick what you have handy):
- Your ticket number or order ID (if you have one)
- Product or service involved
- A brief summary of the problem and the most recent error message (if any)
- What you’ve already tried (steps you took to fix it)
- Your environment (device, OS, browser or app version)
- How this is impacting you (severity/priority)
- Any screenshots or logs you can attach

What I can do next:
- Escalate to a supervisor or a higher-tier team and mark it as urgent.
- Open a new ticket with a clear, prioritized description if the old one isn’t moving.
- Arrange a callback or live chat with a specialist.
- Share a concise plan and ETA for resolution if you prefer.

If you’d like me to start an escalation right now, say “Escalate,” and include as much of the above as you can. If you can’t gather everything, I can still proceed with what you have and fill in the rest from the ticket history.

---

## a1
**Q:** It's broken, fix it.

**Expected:** ask_clarifying_question (escalation required: False)

**Baseline answered:** I’m sorry it’s not working. I can help fix it. To get you back up quickly, I need a bit more detail.

Please tell me:
- What product or service is broken (name and version)?
- Are you using web, iOS, Android, Windows, macOS, or a hardware device?
- A brief description of the issue and any exact error messages or codes.
- When it started, and if anything recent changed (updates, settings, new hardware, etc.).
- Steps to reproduce, if possible.
- Your device specs and network (e.g., iPhone with iOS 16, Windows 10, Chrome browser, Wi‑Fi).
- A screenshot or screen recording would help.

If you want to try something now, here are quick checks you can run based on the type of problem:

- Software/app:
  - Close the app and reopen. If possible, reboot the device.
  - Check for updates and install them.
  - Clear app cache/data or reinstall the app.
  - Sign out and sign back in.

- Web:
  - Try a different browser or an incognito/private window.
  - Clear browser cache and cookies, disable extensions.
  - Check the service/status page if available to see if there’s a known outage.

- Hardware/device:
  - Power cycle the device, unplug/reconnect power, check all cables.
  - Look for status lights or error codes and note them.
  - Check for firmware updates via the official app or support site.
  - If safe, perform a factory reset after backing up data (if applicable).

If you’d like, I can guide you step by step through a tailored troubleshooting path once you share the product and platform. If it looks like a hardware issue or a service outage, I can also help file a repair ticket or arrange escalation.

---

