# Windows x64 Local Desktop — Experimental Preview

Download [Nora Desktop installer](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Setup-v1.1.1-Windows-x64-Experimental.exe).

1. Run the installer. Installation is per-user and initializes required UI components.
2. Open Nora from the Start menu or Desktop. The bundled signed Runtime initializes and verifies License / DataPack automatically.
3. Click **鲜食制作**, enter pet details, select ingredients, calculate and view the returned formula.

Windows 10/11 x64 with .NET Framework 4.8 is the desktop target. The installer prepares Microsoft Edge WebView2 if missing, using Microsoft's signature-verified installer; this initial dependency step needs internet. Installed formulation runs locally. The GUI installer and full UI-to-Runtime smoke are tested on a real Windows Server 2022 x64 runner, not on an independently provisioned Windows 11 clean machine.

Windows x64 is **Experimental Preview**, with **no production support**. The existing native 160-case comparison has 61 exact matches, 97 internal numeric differences and 2 user-affecting differences: **158/160 user business results are equivalent; one case changes ingredient gram allocation and one case has a Solver timeout**. This is not a 160/160 pass or production validation. Use for evaluation, testing and integration only, not formal production nutrition decisions. The full comparison was not rerun for this Desktop packaging update.

Code signing and final clean-machine acceptance are WAIVED_BY_OWNER, not PASS. Unknown Publisher / SmartScreen warnings may appear. Enterprise policy may prevent unsigned Preview execution.

The app installs under the current user's LocalAppData Programs/Nora directory. Runtime state stays in LocalAppData Nora/DesktopRuntime; WebView storage stays in Nora/DesktopWebView. Quit stops the Desktop Runtime. Uninstall through Windows Settings; user Runtime records are retained for reinstall. Remove those Nora state folders after quitting if you want to erase them. An installer reinstall refreshes the GUI; newer engine bundles remain subject to authenticated version checks. No automatic update service is claimed.

Community is free for personal, company and commercial use, including Local and Self-hosted deployment. The bundled universal signed Community License has no device binding, machine-code submission, activation server or manual approval. Reasonably display **Powered by Nora · PalEcho**. Commercial / Enterprise attribution removal is available through a separate license, including white-label / OEM authorization. SDK: Apache-2.0. Runtime and DataPack: Proprietary.
