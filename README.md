# Nora

**Open SDK. Private Engine. Local or Self-hosted.**

Fresh-food formulation for dogs and cats. Open SDK. Private Runtime. Private DataPack.

## Downloads — v1.1.1 Community Preview

| Platform | Local Desktop | Self-hosted Runtime |
| --- | --- | --- |
| macOS Apple Silicon, macOS 14+ | [Local Community Preview DMG](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-v1.1.1-macOS-ARM64-Community-Preview.dmg) | [Self-hosted Community Preview TAR.GZ](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-macOS-ARM64.tar.gz) |
| Windows x64 | [Local Experimental Preview EXE](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Setup-v1.1.1-Windows-x64-Experimental.exe) | [Self-hosted Experimental Preview ZIP](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-Windows-x64-Experimental.zip) |
| Linux x64, Ubuntu 24.04 | Not offered | [Experimental Self-hosted Preview TAR.GZ](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-Linux-x64-Experimental.tar.gz) |

[Release notes](https://github.com/wangsong423258-blip/nora-formulator/releases/tag/v1.1.1-preview) · [SHA256 checksums](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/SHA256SUMS.txt) · [Manifest](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/RELEASE_MANIFEST.json)

### Local Desktop

Download → install → open **Nora** → click **鲜食制作** → enter your pet's details → choose ingredients → calculate → view the formula.

The same Desktop UI is used on Mac and Windows. The application initializes the local Runtime, verifies the included Community License and encrypted DataPack, and displays the Runtime's formulation response. No Python, compiler, development checkout, device application or manual DataPack setup is needed.

- **Mac:** open the DMG, drag Nora.app to Applications and launch it. [macOS installation](docs/macos-local.md).
- **Windows:** run the EXE and open Nora from the Start menu or Desktop. The installer prepares Microsoft Edge WebView2 if missing; initial dependency installation needs internet. Calculation then runs locally. Windows 10/11 x64 with .NET Framework 4.8; native GUI smoke tested on Windows Server 2022 x64. Unsigned Preview may show Unknown Publisher / SmartScreen prompts. [Windows installation](docs/windows-local.md).

Apple Developer ID signing, notarization and final clean-machine acceptance are **WAIVED_BY_OWNER**, not PASS. This app is not Apple notarized. First launch may require manual approval in **System Settings → Privacy & Security**. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。

### Self-hosted

Extract the Runtime archive on your own Mac, Windows PC, Windows Server or Linux x64 host/server. No GUI is required. Your own backend, website or app can integrate with the local Runtime using the public SDK / CLI; core calculation does not depend on PalEcho cloud services. Keep the connection credential inside your trusted backend.

Mac:

```sh
./nora install
./nora start
./nora status
```

Windows:

```powershell
.\cli\nora.cmd install
.\cli\nora.cmd start
.\cli\nora.cmd status
```

Linux (Ubuntu 24.04 x64):

```sh
./cli/nora install
./cli/nora start
./cli/nora status
```

[Linux Self-hosted](docs/linux-self-hosted.md) · [macOS Self-hosted](docs/macos-self-hosted.md) · [Windows Self-hosted](docs/windows-self-hosted.md) · [SDK integration](docs/integration.md)

### Validation and Preview limits

macOS ARM64 remains the **validated reference platform: 160/160 EXACT** on the frozen reference. The engine, nutrition data and Canonical Contract are unchanged. This update checks the final GUI/package and a bounded formulation smoke; it does not claim a new full regression or an independent clean-machine acceptance run.

Windows x64 is **Experimental Preview**, with **no production support**. The existing native 160-case comparison has 61 exact matches, 97 internal numeric differences and 2 user-affecting differences: **158/160 user business results are equivalent; one case changes ingredient gram allocation and one case has a Solver timeout**. This is not a 160/160 pass or production validation. Use for evaluation, testing and integration only, not formal production nutrition decisions. The full comparison was not rerun for this Desktop packaging update.

Windows code signing and final clean-machine acceptance are **WAIVED_BY_OWNER**, never PASS. Automatic OS service registration and reboot recovery for Self-hosted are not certified by this Preview. Linux provides Self-hosted only, without a Desktop GUI or installer. macOS Intel and Windows ARM64 are outside the supported Preview targets.

Linux x64 is **Experimental Self-hosted Preview**, with **no production support**. The existing Ubuntu 24.04 x64 native 160-case audit has 61 exact matches, 96 internal numeric differences, 1 display-equivalent result and 2 user-affecting differences: **158/160 user business results are equivalent; one case changes ingredient gram allocation and one case has a Solver timeout**. The timeout is included in the two user-affecting cases. Use for evaluation, testing and integration only, not formal production nutrition decisions. No numerical regression was rerun for this publication.

## Community / Commercial licensing

Community is free for personal, company and commercial use, including Local and Self-hosted deployment. The bundled universal signed Community License has no device binding, machine-code submission, activation server or manual approval. Reasonably display **Powered by Nora · PalEcho**. Commercial / Enterprise attribution removal is available through a separate license, including white-label / OEM authorization. SDK: Apache-2.0. Runtime and DataPack: Proprietary; they are not included in this repository and are distributed only as separate Release assets.

Local and Self-hosted have the same algorithm capabilities, Engine version, DataPack version, License schema and Canonical API. [Licensing](docs/licensing.md) · [Attribution](docs/attribution.md) · [Security](docs/security.md).

## Public SDK

SDK 0.3.2 requires Node.js 22+ for developer integration. The included native Runtime and Desktop do not require Node.js. Canonical API v1 retains its 96 operations. GitHub source archives contain the public SDK, not the native Runtime installation.

```js
import { NoraClient } from 'nora-sdk';
// Read the protected Runtime connection file only in your trusted backend.
const client = new NoraClient(connection);
const status = await client.runtimeStatus();
```

Never expose the connection token in browser code or public logs. The HTTP adapter is an integration layer. [OpenAPI](openapi/openapi.json) · [Contract](docs/contract.md) · [Examples](examples).

## Contact & Commercial Licensing

For Commercial / Enterprise licensing, removal of the “Powered by Nora · PalEcho” attribution, enterprise self-hosted deployment, product integration, OEM / white-label licensing, or business collaboration, please contact:

- Website: [https://www.PalEcho.com](https://www.PalEcho.com)
- Email: wangsong423258@gmail.com

For technical issues, please use GitHub Issues. For security-related reports, please refer to SECURITY.md.
