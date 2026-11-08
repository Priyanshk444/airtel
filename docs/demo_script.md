# Demo script (3 minutes)

Before the demo: `docker compose up`, open http://localhost:3000 in a phone-sized window, and have the Partner
tab open in a second tab. Reset the database with `docker compose down -v` if you want a clean run.

**0:00 - 0:20 · The problem (one breath)**
"Only 7 in 100 small-business leads get activated, after 18 days and 3 chasing calls. 59% of drops are our own
process. We built the journey a shop owner can finish on a phone in one sitting, in Hindi or English."

**0:20 - 1:00 · Advisor**
Tap *Start with the advisor*. If the chat model is available, type in Hinglish:
"Nashik mein kirana hai, 3 log, GST nahi hai par Udyam hai, internet aur WhatsApp chahiye."
Otherwise use *Tap answers*: Kirana, Nashik, 3 staff, "No, but I have Udyam", tick WhatsApp.
Point out: the bundle comes with a reason per line, WhatsApp is *excluded* with the exact reason (needs a GSTIN),
and the price is one monthly number. "The model only talks. A rule engine decides, so it cannot invent a product
or a price."

**1:00 - 1:30 · Quote and checkout**
*Continue to quote*. Flip customer Wi-Fi on; the price updates instantly. *Proceed to checkout*, pick UPI, type
anything, place the order. Expected activation date is shown.

**1:30 - 2:20 · Smart KYC**
*Verify my business*. Show the consent screen: four separate purposes, only verification required. Agree.
Choose sample applicant **K11**, tap *Use sample* on each document: it fails because the electricity bill is
257 days old. Switch to **K02**: skewed scan, a 0 read where an O belongs, repaired, confirmed active in the
registry, routed to review. Then **K12**: verified, order moves to "KYC verified".
"Fifteen checks, every one explained in plain words. Identifiers are masked everywhere."

**2:20 - 2:40 · Tracker**
*Track my installation*: timeline with expected dates. Tap *simulate next step* twice. "No more calls to ask
where my order is."

**2:40 - 3:00 · Partner view**
Second tab, *Partner*. Handoffs: a lead the advisor could not close, with the summary, filtered to Maharashtra.
*Who to call*: the ranked list with its honest held-out numbers (AUC 0.69, 2.2x lift in the top 10%).
"Partners get leads from the app instead of competing with it."
