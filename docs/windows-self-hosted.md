# Windows x64 Self-hosted Edition

Target: Windows x64 PCs and Windows Server x64.

Planned asset: `Nora-Runtime-v1.1.1-Windows-x64-Experimental.zip`.

**Release withheld: no runnable Windows PE Runtime is available.** No ZIP Runtime is published in v1.1.1-preview. Native 160-case validation and Windows Server acceptance are NOT MEASURED. Any future unvalidated package is Experimental Preview for evaluation, testing and integration only, and must not be used for production nutrition decisions.

The intended archive contains `runtime/`, `data/`, `license/`, `config/`, `cli/` and `docs/`. Deployment is extract → install on your host → import a publisher-issued license and matching device grant → start → integrate your backend. The CLI interface is `nora install`, `nora start`, `nora stop`, `nora status` and `nora update`. These are planned deployment instructions, not evidence of a working Windows archive.

Background operation, permissions, restart recovery, persistent DataPack and license paths, and enterprise backend integration still require native Windows Server testing. No validated Windows service integration is provided here.

The architecture keeps authorized calculation and user data on enterprise infrastructure without a PalEcho cloud calculation dependency. An optional local HTTP adapter is an integration layer. Local and Self-hosted are intended to share the same engine, encrypted data version and calculation capabilities. Community self-hosting is free with **Powered by Nora · PalEcho**. See [licensing](licensing.md).
