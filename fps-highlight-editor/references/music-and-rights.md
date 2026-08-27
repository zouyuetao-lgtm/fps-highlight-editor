# Music and rights

Use this reference only when music mode is `provided` or `licensed-web`. Preserve game audio unless the manifest target explicitly says otherwise.

## Provided music

Inventory the supplied tracks and compare mood, duration, BPM, arrangement, lyrics or language suitability, and fit with the approved segment sequence. Before proposing or approving user-provided commercial music, warn that platforms may trigger copyright claims, muting, reach restrictions, or monetization limits. Set `approval_confirmed: true` only after the user accepts that warning. Reference the exact approved local copy with `music_copy_artifact_id` and existing publication-rights evidence with `authorization_artifact_id`. Attribution alone is not authorization.

## Licensed web music

Create a shortlist before acquiring anything. For each option record title, creator, licensing service, URL, license scope for the intended export, price or subscription condition if shown, and why it fits. Ask for approval of the selected option and its licensing terms before download, purchase, or use. Save approved evidence as a `license` artifact and reference it with `authorization_artifact_id`; reference the exact acquired copy with `music_copy_artifact_id` and set `approval_confirmed: true`.

## Edit and mix proposal

Align cuts, beat drops, or transitions to measured BPM and musical phrases rather than assuming a tempo. Keep music below important game cues and use sidechain compression or volume automation so speech, impacts, and game events remain intelligible. State track, license record, beat alignment, and mix targets in the proposal; render only after that proposal is approved.
