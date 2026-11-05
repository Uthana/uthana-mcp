# What each operation costs

Uthana charges for creating motion and characters. Looking things up, estimating, previewing and exporting what you already own do not cost anything. Rates are the same as in the Uthana web app and API and are listed on [uthana.com/pricing](https://uthana.com/pricing), which stays the source for current rates. There is no separate fee for the MCP, for API calls, or per agent token. Your assistant provider's own charges, if any, are separate.

## Charged operations

| Operation | MCP tool | Rate | What is measured |
| --- | --- | --- | --- |
| Text-to-Motion 3.0 | `generate_motion` | $0.10 / s | Seconds of generated motion |
| Text-to-Motion 2.0 | `generate_motion_v2` | $0.03 / s | Seconds of generated motion |
| Video-to-Motion 2.0 / 2.1 | `generate_motion_from_video` | $0.05 / s | Seconds of generated motion, usually about the length of the video clip |
| Locomotion 1.0 | `generate_locomotion` | $0.02 / s | Seconds of generated motion; length follows strides, not a requested duration |
| Stitching and looping 2.0 | `stitch`, `create_looped_motion` | $0.01 / s | Seconds of the new motion, including transition frames |
| Auto-rigging | `upload_character` when Uthana auto-rigs a mesh that has no rig (`auto_rig=true`) | $0.15 / rig | Charged only when auto-rigging runs; choosing `rerig_target` during auto-rig adds nothing |
| Character generation | `create_character_from_image`, `create_character_from_prompt` | $0.75 / character | One charge per finished character |

The charge uses the length of the motion Uthana actually produced, which can differ slightly from the length you asked for. A four-second Text-to-Motion 3.0 request produces 97 frames at 24 FPS (4.04 seconds), so it is estimated at $0.40 and charged $0.4042.

A failed generation is not charged. A retry, or another generation of the same prompt, is a new operation and is charged again.

## Free operations

- Reading your account, balance and allowances (`get_usage`), listing and searching your own characters and motions (`list_characters`, `list_motions`), reading motion details and job status.
- Cost estimates (`estimate_model_cost`). An estimate never starts work.
- Previews (`get_preview`, `get_preview_frame`).
- Trimming a motion (`trim_motion`) and saving an edited motion (`save_motion`).
- Uploading an already-rigged character (`upload_character`), including converting its skeleton with `rerig_target`.
- Exporting a motion you own onto any character you can access (`download_motion`), in any format.
- Getting a fresh link to an export, or fetching an export that was already made (`get_artifact_download`, `get_request_status`). This reuses the existing file. It does not export or charge again.

Text-to-character previews (`preview_character_from_prompt`) have no published price of their own; the character is charged when you finish it with `create_character_from_prompt`.

## Account types

- **Pay-as-you-go accounts** (all new accounts, and every account created since subscriptions ended in August 2026) pay from one USD balance shared by the web app, API and MCP. New accounts start with $5 of free credit. The credit is spent at the same rates as paid credit; it does not change any price. Exports are unlimited.
- **Older subscription plans** are not charged per operation. They keep their monthly download allowance, counted in seconds of motion exported. Exporting a motion again on a character it was already exported to does not count again. `get_usage` reports this allowance in seconds, separately from any USD balance, and `check_download_allowed` checks one motion and character before you export.
- **Enterprise and contract accounts** are billed under their agreement.

## Spending limits

Paid work uses your account balance. If your balance is too low, add credit in your account settings. Auto top-up is off unless you turn it on there, where you can also set its monthly limit. Because a job is charged when it finishes, jobs that finish close together can briefly leave your balance below zero; that amount comes out of your next credit.

Uthana does not enforce a per-request or per-conversation budget. If you tell your assistant "only if it costs at most $0.50", that is an instruction your assistant follows, not a cap Uthana enforces. Your assistant should estimate first and stop if the estimate is over your limit or the price is unknown.

## Estimates and actual charges

`estimate_model_cost` multiplies the current rate by the quantity you give it. It is an estimate, not a charge. After work finishes, the MCP reports a charge only when it has billing evidence. Otherwise it reports the cost as unmeasured, and your account's transaction history in the Uthana app shows the exact amount.

If you run out of credit, add credit in your account settings and ask your assistant to continue the same task. It should not switch to a cheaper model, buy credit, or start the work again without asking you.
