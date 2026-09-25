# Nora

**Open SDK. Private Runtime. Private DataPack.**

Developer interfaces for Nora, a formulation system for canine and feline fresh diets.

## Downloads — v1.1.1 Community Preview

[Release page](https://github.com/wangsong423258-blip/nora-formulator/releases/tag/v1.1.1-preview) · [Release manifest](RELEASE_MANIFEST.json) · [Checksums](SHA256SUMS.txt)

**This preview publishes the SDK, documentation and release status metadata only. No installable Runtime or DataPack is available in this release.** GitHub's source archives contain the SDK; they do not install Nora or perform formulation by themselves.

| Edition | Target | Runtime download | Status |
| --- | --- | --- | --- |
| Local | macOS Apple Silicon / ARM64 | Not available | Community Preview planned |
| Self-hosted | macOS Apple Silicon / ARM64 | Not available | Community Preview planned |
| Local | Windows x64 | Not available | Experimental Preview withheld |
| Self-hosted | Windows x64 / Windows Server | Not available | Experimental Preview withheld |

**macOS Apple Silicon is the validated reference platform: 160/160 exact regression** on the existing native reference candidate (138 current + 22 compatibility cases). This result does not establish clean-machine acceptance of a final installer. A usable distribution still needs its encrypted DataPack, publisher-issued authorization and verified release bundle.

Apple Developer ID signing and notarization have not been completed. For a future unnotarized Community Preview, first opening may require the user to allow Nora manually in macOS **System Settings → Privacy & Security**. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。

**Windows x64: Experimental Preview planned; no runnable Windows Runtime is published.** Native 160-case validation has not been completed or evidenced. Windows is not production validated and must not be used for production nutrition decisions. A future Experimental package is for evaluation, testing and integration only.

## Choose a deployment

- **Local Edition:** intended for personal and company computers. Download an available installer, install the Runtime, encrypted DataPack and license, then run locally. [macOS Local](docs/macos-local.md) · [Windows Local](docs/windows-local.md).
- **Self-hosted Edition:** intended for companies and developers running on their own Mac, Windows PC or Windows Server. Their applications and backends integrate through the SDK or CLI, with an optional local adapter. [macOS Self-hosted](docs/macos-self-hosted.md) · [Windows Self-hosted](docs/windows-self-hosted.md).

Both editions are designed to use the same Nora Engine, DataPack version, license schema, Canonical Contract and calculation capabilities. Authorized calculation runs on the user's infrastructure without a PalEcho cloud calculation service. The adapter is an integration option. Linux, macOS Intel and Windows ARM64 are outside Nora v1 scope.

## Licensing

Apache-2.0 applies only to this public SDK repository. Nora Runtime and Nora DataPack are Proprietary and are not included in this repository or licensed under Apache-2.0.

Community is free for personal, company, commercial, local and self-hosted use. Reasonably display **Powered by Nora · PalEcho**. A separate Commercial / Enterprise authorization can remove attribution and may cover white-label, OEM and enterprise offline deployments. Local and Self-hosted have the same calculation capabilities. See [licensing](docs/licensing.md), [attribution](docs/attribution.md), [license metadata](LICENSE_INFO.md) and [security](docs/security.md).

## SDK quick start

The public package is `nora-sdk` version 0.3.1; the target Runtime version is 1.1.1. Node.js 22 or later is required for these developer tools. From a checkout of this repository, inspect the CLI without installing a Runtime:

```sh
node cli/nora.mjs --help
```

The Canonical API remains v1 with 96 operations. The SDK can be reviewed and integrated now; formulation requires a separately supplied, verified Runtime bundle. Public installation remains disabled until publisher trust configuration is provisioned.

## Local integration

Node.js 22 or later is required. Once an official signed distribution is available:

```sh
nora install --bundle /path/to/signed-distribution
nora enroll
nora license import /path/to/license.json --grant /path/to/device-grant.json
nora start
nora status
nora version
nora stop
nora update --bundle /path/to/new-signed-distribution
nora uninstall
```

The installer accepts an offline bundle, verifies its publisher signature, platform, compatibility versions and every file, and installs the Runtime and encrypted Data Pack. Enroll the device, obtain a signed Community license and matching device grant from the publisher, then import them. Community users do not self-sign licenses. Commercial licenses use the same import flow and calculation capabilities. Neither initial offline import nor subsequent calculation requires a PalEcho calculation service.

Device enrollment uses the platform credential store by default. If that store is unavailable, explicitly select `nora enroll --provider passphrase`; the Runtime prompts for the unlock passphrase. Keep it out of application settings and command arguments. A valid device grant is required after replacing a device identity or license.

Updates verify the new signed release before activation, retain the previous signed release for recovery, reject version downgrades and check authorization compatibility. A running instance is stopped before switching and restarted after validation. Failed validation restores the previous installation pointer. `nora uninstall` stops the authenticated Runtime, removes its local authorization and device key, and removes only the dedicated installation directory. It refuses unknown files or links. Remove the SDK separately with your package manager. All commands accept `--home DIR`; the default home is the user's `.nora` directory. Use a new directory for the first installation.

**Release status:** production signing authority and official platform certificates have not been provisioned. This SDK intentionally has empty production trust pins and refuses installation until a reviewed publisher release supplies them. These commands describe the distribution interface and do not imply that an official downloadable binary or self-issued production license is available.

```js
import { NoraClient } from 'nora-sdk';
import { createAttribution } from 'nora-sdk/attribution';

// Load the connection credential from your local Runtime's protected connection file.
const client = new NoraClient({ token: process.env.NORA_API_TOKEN });
const status = await client.runtimeStatus();
const result = await client.call('selected_ingredient_meals__validateQuickMealProfile', {
  body: { profile: { species: 'DOG', weight_kg: 10 } },
});
// In a browser UI, render createAttribution({ document, locale: 'zh' }) in a visible location.
```

The default endpoint is `http://127.0.0.1:8765`. HTTP is accepted only for the literal loopback address; HTTPS remains available for explicitly configured integrations. Runtime credentials are separate from license signatures. Do not embed credentials in distributed frontend code. Default Runtime browser-origin policy requires applications to call through their own trusted local/backend integration; it does not expose a permissive CORS service.

Canonical v1 retains its 96 reviewed operations and separate capability resources. Runtime status is a separate `/runtime/v1/status` endpoint. See [integration](docs/integration.md), [attribution](docs/attribution.md), [contract](docs/contract.md), and [OpenAPI](openapi/openapi.json).
