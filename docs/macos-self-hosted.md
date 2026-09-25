# macOS Self-hosted — Community Preview

Requires an Apple Silicon / ARM64 Mac running macOS 14+.

[Download Runtime TAR.GZ](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-macOS-ARM64.tar.gz) · [Checksums](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/SHA256SUMS.txt)

Extract and run from the extracted directory:

```sh
./nora install
./nora start
./nora status
./nora stop
```

The archive includes runtime/, data/, license/, config/, cli/ and docs/. The encrypted DataPack and universal Community License reside inside the authenticated runtime/ bundle. Installation verifies them automatically. No machine code, device grant, registration or manual approval is required. No Python, Node.js, compiler or private checkout is required.

The default installation is the current user's .nora directory. Use --home DIR consistently for a dedicated service account. Connection credentials are private to that account. Run `./nora update --bundle /path/to/new/runtime` for a newer authenticated bundle, or `./nora uninstall` to remove the local installation. The native CLI can be invoked from your own process supervisor. Automatic operating-system boot registration is not installed by this Preview.

Your application, website backend or enterprise service can use the public SDK or local adapter on your own host. Calculation and user data can remain on your infrastructure; no PalEcho activation or cloud calculation service is required. The local HTTP adapter is an integration option. Local and Self-hosted use an identical Runtime bundle, encrypted data version, license schema and Canonical Contract.

Apple signing, notarization and final clean-machine acceptance are WAIVED_BY_OWNER. macOS may require first-open approval in System Settings → Privacy & Security. Community is free with **Powered by Nora · PalEcho** attribution. See [integration](integration.md) and [licensing](licensing.md).
