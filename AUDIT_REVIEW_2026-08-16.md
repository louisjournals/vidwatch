# my-vidwatch audit review — 2026-08-16

## Record status

The original untracked review file was not present in the repository, elsewhere under
`/Users/louistan`, or in Trash when Group E was closed on 2026-08-17. This file is a
**recovered closeout record**, not a reconstruction of unavailable prose. It records
only the review findings explicitly referenced by the accepted closeout instructions;
no unspecified review content is invented.

## Review 2 and Review 6 — detector failure must be loud

Acceptance requirement: every ffmpeg/ffprobe detector must distinguish a successful
zero-result run from a non-zero process exit. A non-zero exit raises `VidwatchError`
with the stderr tail. Coverage includes `detect_cuts`, `keyframe_times`,
`detect_silence`, `dedup.content_changes`, and every detector in `defects`.
`cmd_read` must also guard empty extraction before indexing the first kept frame.

Closeout: implemented and covered by explicit failing-binary tests in `b92bc88a`.

## Review 4 — cold-cache defects reporting

Acceptance requirement: when `defects` has no cached transcript, it must warn that
transcript-based silence suppression did not run; cold-cache output must not be
indistinguishable from a warm-cache run.

Closeout: implemented and tested in `b05b7f53`.

## Review 5 — resolution accounting is pre-dedup

Acceptance requirement: `read` chooses resolution from the pre-dedup frame count, so
frames later dropped by dedup still influenced the resolution budget. `--json` must
report both the pre-dedup resolution-budget count and the post-dedup frame count, and
the Design notes must state this explicitly.

Closeout: implemented and tested in `b05b7f53`.

## Closeout

The referenced review acceptance tests pass in the final Group A-D suite. No detector
thresholds were changed as part of these fixes. Any review item not named above was not
recoverable from the repository or the closeout instructions and is therefore not
silently reconstructed here.
