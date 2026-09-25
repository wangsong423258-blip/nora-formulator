# macOS Local Edition

Target: Apple Silicon / ARM64, macOS 14 or later.

Planned asset: `Nora-v1.1.1-macOS-ARM64-Community-Preview.dmg`.

**Not available in v1.1.1-preview.** The existing native reference has 160/160 exact regression, but a usable final installer and clean-machine acceptance are still pending. This release's source archives are developer tools only.

The intended experience is download → open DMG → install Nora → start → use. The installer must supply the Runtime, encrypted DataPack, license verification, CLI bridge and application directories without a development Python environment or manual environment variables. That complete installation has not been delivered by this preview.

Apple Developer ID signing and notarization are pending. A future unnotarized Community Preview must say so; first opening may require manual approval in macOS System Settings → Privacy & Security. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。 Do not disable system security globally.

Once a usable package is published, verify its checksum and follow its included installation instructions. Community permits personal, company, commercial and local use for free with **Powered by Nora · PalEcho** attribution. See [licensing](licensing.md) and [current downloads](../README.md#downloads--v111-community-preview).
