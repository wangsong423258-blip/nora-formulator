# macOS Self-hosted Edition

Target: an Apple Silicon / ARM64 Mac running macOS 14 or later.

Planned asset: `Nora-Runtime-v1.1.1-macOS-ARM64.tar.gz`.

**Not available in v1.1.1-preview.** No runnable self-hosted bundle is published. Encrypted DataPack provisioning, publisher authorization and final installation acceptance remain pending. Apple signing and notarization are incomplete.

The intended package contains `runtime/`, `data/`, `license/`, `config/`, `cli/` and `docs/`. It installs on a host you control and requires no development Python environment or private source checkout. The current public developer CLI requires Node.js 22 or later.

The following commands describe the integration interface for a future verified bundle; they cannot install this source-only preview:

```sh
nora install --bundle /path/to/signed-bundle
nora enroll
nora license import /path/to/license.json --grant /path/to/device-grant.json
nora start
nora status
nora stop
nora update --bundle /path/to/new-signed-bundle
```

The license and matching device grant must be issued by the publisher. Integrate your backend through the SDK or CLI; an optional local HTTP adapter is only an integration layer. Calculation and user data can remain on your own infrastructure without a PalEcho cloud calculation service. Local and Self-hosted use the same calculation capabilities and version contract. Community self-hosting is free with **Powered by Nora · PalEcho** attribution. See [licensing](licensing.md).
