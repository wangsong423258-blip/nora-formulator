# Nora

**Open SDK. Private Runtime. Private DataPack.**

Local formulation Runtime and developer interfaces for canine and feline fresh diets.

## Downloads — v1.1.1 Community Preview

| Edition | Platform | Download | Status |
| --- | --- | --- | --- |
| Local | macOS Apple Silicon / ARM64 | [DMG](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-v1.1.1-macOS-ARM64-Community-Preview.dmg) | Community Preview |
| Self-hosted | macOS Apple Silicon / ARM64 | [TAR.GZ](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-macOS-ARM64.tar.gz) | Community Preview |
| Local | Windows x64 | Windows package pending | Experimental Preview / Full Native Validation Pending |
| Self-hosted | Windows x64 / Windows Server | Windows package pending | Experimental Preview / Full Native Validation Pending |

[Release notes](https://github.com/wangsong423258-blip/nora-formulator/releases/tag/v1.1.1-preview) · [SHA256 checksums](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/SHA256SUMS.txt) · [Release manifest](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/RELEASE_MANIFEST.json)

**Community is ready to use without registration:** the Mac packages include a universal signed Community License and encrypted DataPack. No device binding, machine-code submission, activation server, contact with PalEcho or manual approval is required. Personal, company, commercial, Local and Self-hosted use are free. Reasonably display **Powered by Nora · PalEcho**.

### macOS Local

1. Download the DMG, open it and drag **Nora.app** to **Applications**.
2. Launch Nora and select **Install & Start**. The Runtime automatically verifies the included License and DataPack.
3. Use **Status** to confirm readiness; connect your application using the public SDK. **Stop** stops the Runtime; closing the manager window leaves it running.

Apple Developer ID signing, notarization and final clean-machine acceptance are **WAIVED_BY_OWNER**, not PASS. This Preview is unnotarized. First opening may require manual approval in **System Settings → Privacy & Security**. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。 See [macOS Local](docs/macos-local.md).

### macOS Self-hosted

Extract the TAR.GZ on an Apple Silicon Mac running macOS 14 or later. From the extracted directory:

```sh
./nora install
./nora start
./nora status
```

No Python, compiler, Node.js or development checkout is required for the included native CLI and Runtime. Your application, website backend or enterprise service can call the Runtime on your own infrastructure. Core calculation does not require a PalEcho cloud service. See [Self-hosted deployment](docs/macos-self-hosted.md) and [integration](docs/integration.md).

### Platform evidence

macOS Apple Silicon remains the **validated reference platform: 160/160 exact regression** on the existing native reference. The Core binary and mathematical/data inputs are unchanged. This release checks installation, automatic Community authorization, a bounded formulation smoke, restart and tamper rejection; it does not claim a newly executed full 160-case or independent clean-machine run.

**Windows x64 is Experimental Preview / Full Native Validation Pending. 尚未完成完整 Native 数值验证。** Native 160-case regression, Windows code signing and final clean-machine acceptance are WAIVED_BY_OWNER, not PASS. No runnable Windows PE Runtime could be built in the available environment, so no Windows EXE/ZIP is uploaded. Windows package pending. No production support; future Experimental packages are for evaluation, testing and integration only and must not be used for production nutrition decisions.

**Linux is not in Nora v1 scope.** macOS Intel and Windows ARM64 are also outside v1 scope.

## Licensing and deployment

Apache-2.0 applies to this public SDK repository. Nora Runtime and DataPack are Proprietary, are not included in this repository, and are distributed as separate Release assets under their own terms.

Community permits free personal, company, commercial, Local and Self-hosted use with **Powered by Nora · PalEcho** attribution. A separate Commercial / Enterprise authorization can remove attribution and allow white-label or OEM use. Local and Self-hosted use the same engine, DataPack version, license schema, Canonical Contract and calculation capabilities. See [licensing](docs/licensing.md), [attribution](docs/attribution.md) and [security](docs/security.md).

## Public SDK

SDK 0.3.2 requires Node.js 22+ for developer integration; the bundled native Runtime CLI does not. Canonical API v1 retains its 96 operations. GitHub source archives contain SDK source, not the native Runtime installation.

```js
import { NoraClient } from 'nora-sdk';
// Read the protected local Runtime connection file in your trusted backend.
const client = new NoraClient(connection);
const status = await client.runtimeStatus();
```

Never expose the local connection token in browser code or public logs. The HTTP adapter is an integration layer. See [OpenAPI](openapi/openapi.json), [contract](docs/contract.md) and [examples](examples).
