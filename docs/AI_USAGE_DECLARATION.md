# AI usage declaration

We were asked to be open about how AI was used to build TheOne, so here it is. I used AI in three places: writing the tests, writing the mathematical methods behind the risk scoring, and on the voice side of the product.

## 1. Tests

AI helped me write the automated tests. There are 170 of them, and they cover the detection engine, the payment decisions, ring finding, bank holds and blocks, NIBSS tracing, statement checks, the voice, iris and phone checks, and Ziva's tools.

I decided what each test needed to prove, for example that a victim who paid into a ring is never flagged, or that a held payment cannot be released by biometrics alone. AI then helped me write the test code and the fake data for it, such as a synthetic mule ring and synthetic voices and eyes. I run the full suite before every change goes in.

## 2. Mathematical methods

AI helped me write the maths that turns transfers into decisions:

- **Warning-sign rules:** sliding time windows to count new senders, and first-in-first-out matching to see how fast money leaves an account after it arrives.
- **Combining signs into one score:** a probability formula (noisy-OR), so each extra warning sign raises the risk without the score ever going past 100.
- **Following the money:** passing risk forward to the accounts that quickly receive money from a flagged one, up to three steps, and never back to the victims.
- **Finding rings:** grouping linked accounts with union-find, and matching rings between runs so a ring keeps its number as it grows.
- **Checking the sender:** comparing each payment with the customer's own history, including the distance from where they usually pay.
- **Learning from confirmed cases:** adjusting each rule's weight from analyst outcomes, held close to its starting value so a few cases cannot swing it.
- **The shadow model:** a small logistic regression that runs beside the rules but does not make decisions.

The choices behind the maths are mine: which warning signs matter for Nigerian mule accounts, where the flag and hold lines sit, and the safety rules (victims are never scored, a hold never releases on its own). AI helped me turn those choices into working formulas and code.

## 3. Voice

AI powers the voice side of TheOne:

- **Ziva, the analyst assistant,** runs on Google's Gemini Live model. It listens to the analyst, answers out loud and looks up rings and accounts through TheOne's own read-only tools. It cannot take actions; holds and blocks are still clicks in the console. AI also helped me tune how Ziva performs: the Nigerian accent, keeping her to English, cutting out echo from her own voice, and matching misheard names to the right account.
- **Voice verification** uses a pretrained neural speaker model (3D-Speaker ERes2Net, run through sherpa-onnx) to turn a voice into a voiceprint. I set and checked its thresholds on a public speech dataset (LibriSpeech).

## What this means for the results

Every detection number shown in the demo comes from synthetic Nigerian transfer data with planted mule rings, not from a real bank. The next step is to test TheOne on a real bank's past payments.

Kingsley Udoma and Opeyemi Ogunsanya
