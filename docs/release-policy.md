# Release policy

Public source is controlled by the default-deny PUBLIC_MANIFEST.json and reviewed file hashes. Runtime assets must actually run and pass the source, data, secret, private-key, path and baseline-exposure checks before upload. Missing assets are explicitly pending and have no fake hash or download link.

This Community Preview uses the owner's explicit waivers for Apple signing, notarization and final clean-machine acceptance. Windows also has a waiver for full native 160-case validation and code signing. WAIVED_BY_OWNER never means PASS. Windows still requires a runnable PE Runtime before any EXE/ZIP may be published.

Community licenses and DataPacks are universal and signed, with no device registration or manual approval. Platform-signing waivers do not waive the publisher signatures, encrypted data integrity or automatic license validation. Private signing keys never enter the project, public source or release assets.

Local and Self-hosted use the same native engine and version contract. Existing ARM64 160/160 exact reference evidence is retained; this packaging change does not imply a new full-regression or independent clean-machine run. Windows production support remains NO.
