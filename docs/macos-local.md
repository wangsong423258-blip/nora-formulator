# macOS ARM64 Local Desktop

Download [Nora Community Preview](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-v1.1.1-macOS-ARM64-Community-Preview.dmg). Requires Apple Silicon and macOS 14+.

1. Open the DMG and drag Nora.app to Applications.
2. Launch Nora. Runtime installation and signed License / DataPack verification happen automatically.
3. Click **鲜食制作**, complete the existing pet input flow, choose ingredients and calculate.
4. Review ingredient grams, aggregate nutrients, constraint status and warnings returned by Runtime. A recipe does not imply complete balance unless Runtime explicitly states it.

Apple Developer ID signing, notarization and final clean-machine acceptance are **WAIVED_BY_OWNER**, not PASS. This app is not Apple notarized. First launch may require manual approval in **System Settings → Privacy & Security**. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。

Desktop uses the current user's `.nora-desktop` folder. Self-hosted uses a separate `.nora` folder by default. Quitting Desktop stops its own Runtime. To uninstall, quit Nora, remove Nora.app and remove `.nora-desktop` if you want to erase local Runtime records. To refresh this Preview, quit and replace Nora.app with the newly downloaded app. Newer engine bundles must pass the authenticated Runtime update checks; this package does not add an automatic update service.

The native Desktop end-to-end smoke was performed from the final DMG on the existing Mac. It is not an independent clean-machine certification. macOS ARM64 frozen reference remains 160/160 EXACT.

Community is free for personal, company and commercial use, including Local and Self-hosted deployment. The bundled universal signed Community License has no device binding, machine-code submission, activation server or manual approval. Reasonably display **Powered by Nora · PalEcho**. Commercial / Enterprise attribution removal is available through a separate license, including white-label / OEM authorization. SDK: Apache-2.0. Runtime and DataPack: Proprietary.
