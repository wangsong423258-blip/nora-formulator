# Release policy

Every public file must appear in the default-deny PUBLIC_MANIFEST.json with its approved byte hash. The manifest's own hash is retained in the publisher's separate audit record to avoid self-reference. New or modified files require review before the whitelist is updated.

SDK and Runtime publication have separate gates. This v1.1.1-preview publishes the SDK and status metadata only. Runtime packages are withheld until they are actually runnable, contain an authorized encrypted DataPack and pass their applicable distribution checks. A container without those components is not a downloadable Runtime.

The installer validates publisher signatures, platform, compatibility versions and file hashes. It refuses extra files, links, altered content and untrusted releases. Production trust remains empty in the current public SDK; development signing material is never published or accepted as a production authority.

Nora v1 targets macOS ARM64 and Windows x64. An unnotarized macOS Community Preview must disclose its signing status. Windows without native 160-case validation must be Experimental and restricted to evaluation, testing and integration. No Windows release is permitted without a runnable PE Runtime. Production release additionally requires native numerical acceptance, clean installation lifecycle tests and applicable platform signing.

Only actually available assets receive hashes and download links. Missing assets remain unavailable with null hashes in RELEASE_MANIFEST.json. No package, upload or validation result is inferred from a planned filename.
