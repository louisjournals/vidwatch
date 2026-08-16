# my-vidwatch contributor rules

These rules are skill-scoped to `my-vidwatch`.

- No outbound model calls, API keys, non-stdlib dependencies, or audio egress. Keep operation host-agnostic.
- Every default or threshold stated in docs must be measured and traceable to a single code constant. Exception: third-party vendor token models may be derived from the vendor's public processor configuration; mark those figures provisional and keep a calibration TODO until API-reported usage is available.
- Every detector needs a test proving it fails loudly, not only one proving it succeeds quietly.
- Audit findings are worked or explicitly recorded as outstanding. Never list an audit as a deliverable while leaving its findings open without saying so.
- Stage only files touched for the current change. Leave unrelated working-tree changes alone.
