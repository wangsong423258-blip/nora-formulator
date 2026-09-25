# Security and distribution boundary

Only SDK transport, CLI integration, contracts, examples, documentation and attribution components are published here. The calculation engine, nutritional source assets, signing authority and private validation inputs are excluded.

The current preview includes no runnable Runtime or encrypted DataPack. The public installer deliberately rejects bundles until reviewed publisher trust configuration is supplied. Do not add arbitrary trust keys or bypass verification to make an unapproved bundle install.

A future Runtime distribution must authenticate its DataPack signature, version compatibility and integrity, and reject altered content. It must not write a complete decrypted database to disk. The release checksum list detects byte changes; it is not a publisher signature and is not a substitute for the Runtime's trust checks.

Treat a running Nora instance as a local service with protected connection credentials. Keep credentials out of frontend bundles, source control and logs. Integrate through a trusted application backend. An HTTP adapter is optional; calculation does not require a PalEcho cloud service.

macOS signing and notarization are incomplete. Windows code signing, native numerical validation and Windows Server operation are pending. No production security or clean-machine certification is claimed for these unavailable Runtime packages.

Report vulnerabilities using the private procedure in [SECURITY.md](../SECURITY.md). Public issues must not contain credentials, user profiles, service responses or sensitive reproduction data.
