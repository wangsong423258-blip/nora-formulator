# macOS Local — Community Preview

Requires Apple Silicon / ARM64 and macOS 14+.

[Download Nora DMG](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-v1.1.1-macOS-ARM64-Community-Preview.dmg) · [Checksums](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/SHA256SUMS.txt)

1. Open the DMG and drag Nora.app into Applications.
2. Launch Nora. If macOS blocks the unnotarized application, allow it in System Settings → Privacy & Security. 未完成 Apple notarization，首次打开可能需要用户在 macOS 隐私与安全性中手动允许。
3. Select Install & Start. The universal signed Community License and encrypted DataPack are included and verified automatically.
4. Select Status and connect your application through the [SDK](integration.md). Stop ends the background Runtime. Closing the window leaves it running.

No Python, compiler, Node.js, environment-variable setup, device registration or manual license approval is required. No PalEcho activation or cloud calculation server is required. The default installation and protected connection file are in the current user's .nora directory.

Use Uninstall in the manager to remove the Runtime. Remove Nora.app separately if desired. A newer authenticated bundle can be installed with the included CLI's update command; invalid updates are rejected and the previous installation is retained for recovery.

Apple signing, notarization and final clean-machine acceptance are WAIVED_BY_OWNER, not PASS. This is a Community Preview. Existing macOS ARM64 reference evidence remains 160/160 EXACT; full regression was not rerun for this packaging change.

Community is free for personal, company, commercial, Local and Self-hosted use with **Powered by Nora · PalEcho** attribution. See [licensing](licensing.md).
