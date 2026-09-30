# Security and distribution boundary

This repository publishes developer interfaces, Python formulation source and plaintext JSON nutrition data. The original v1.1.1 Runtime and encrypted DataPack downloads remain separate release assets. Signing private keys and publisher tooling are not published.

The plaintext Python engine reads JSON files directly and checks their SHA-256 manifest before calculation. The JSON is readable by anyone with access to this public repository. The manifest detects accidental file changes; it is not a signature or access control.

The original v1.1.1 native Community packages use a universal signed license and an authenticated encrypted DataPack. The license is not device-bound. No registration, manual approval or activation server is needed. The Runtime checks signature, compatibility, full ciphertext integrity and chunk authentication before calculation, and does not write the complete decrypted database to disk.

Publisher signing private keys are retained outside the project in the owner's macOS Keychain. The Runtime contains public signature-verification keys. Offline DataPack reading also requires symmetric decryption material encapsulated in the native reader. This protects packaged storage and avoids a plaintext key file; it is not a claim of resistance to all reverse engineering by a machine owner.

SHA256SUMS.txt verifies published download bytes; it is not itself a digital signature. The included release, License and DataPack envelopes carry publisher signatures. Those signatures are separate from Apple Developer ID and Windows Authenticode. Apple signing, notarization and final clean-machine acceptance are WAIVED_BY_OWNER. Windows native full regression, code signing and final clean-machine acceptance are WAIVED_BY_OWNER, with no Windows package currently published.

Keep the protected local Runtime connection token in a trusted backend and out of browser bundles or public logs. See [SECURITY.md](../SECURITY.md) for private vulnerability reporting.
