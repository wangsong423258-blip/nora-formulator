# Security and distribution boundary

This repository publishes developer interfaces only. Runtime and encrypted DataPack downloads are separate release assets. Signing private keys, source data and publisher tooling are excluded from both repository source and release assets.

Community uses a universal signed license and an authenticated encrypted DataPack. The license is not device-bound. No registration, manual approval or activation server is needed. The Runtime checks signature, compatibility, full ciphertext integrity and chunk authentication before calculation, and does not write the complete decrypted database to disk.

Publisher signing private keys are retained outside the project in the owner's macOS Keychain. The Runtime contains public signature-verification keys. Offline DataPack reading also requires symmetric decryption material encapsulated in the native reader. This protects packaged storage and avoids a plaintext key file; it is not a claim of resistance to all reverse engineering by a machine owner.

SHA256SUMS.txt verifies published download bytes; it is not itself a digital signature. The included release, License and DataPack envelopes carry publisher signatures. Those signatures are separate from Apple Developer ID and Windows Authenticode. Apple signing, notarization and final clean-machine acceptance are WAIVED_BY_OWNER. Windows native full regression, code signing and final clean-machine acceptance are WAIVED_BY_OWNER, with no Windows package currently published.

Keep the protected local Runtime connection token in a trusted backend and out of browser bundles or public logs. See [SECURITY.md](../SECURITY.md) for private vulnerability reporting.
