# Windows x64 Self-hosted — Experimental Preview

Download the [Runtime ZIP](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-Windows-x64-Experimental.zip), extract the entire archive, then open PowerShell in the extracted directory:

```powershell
.\cli\nora.cmd install
.\cli\nora.cmd start
.\cli\nora.cmd status
.\cli\nora.cmd stop
```

The included native PE Runtime installs the universal signed Community License and encrypted DataPack automatically. No Python, compiler, GUI, cloud activation, device registration or manual approval is required. Use on a Windows x64 PC or Windows Server with your own trusted backend, website or app. Calculation stays on your infrastructure.

Pass `--home C:\NoraInstance` consistently to every command for dedicated instance storage; the default is the current user's `.nora` directory. Keep this directory private. Your trusted backend reads its `connection.json` for the loopback address and bearer token; do not copy this token into browser code or expose the adapter directly to the internet. DataPack and License persist in the managed release directory.

```powershell
.\cli\nora.cmd update --bundle C:\NewRelease\runtime --home C:\NoraInstance
.\cli\nora.cmd uninstall --home C:\NoraInstance
```

Update requires a newer compatible signed bundle; failed validation keeps the active version. Stop/start and offline computation were tested on the native runner. Automatic Windows service registration and restart-after-reboot recovery require enterprise deployment configuration and are not certified by this Preview. No general Windows Server production-support claim is made.

Windows x64 is **Experimental Preview**, with **no production support**. The existing native 160-case comparison has 61 exact matches, 97 internal numeric differences and 2 user-affecting differences: **158/160 user business results are equivalent; one case changes ingredient gram allocation and one case has a Solver timeout**. This is not a 160/160 pass or production validation. Use for evaluation, testing and integration only, not formal production nutrition decisions. The full comparison was not rerun for this Desktop packaging update.

Windows code signing and final clean-machine acceptance are WAIVED_BY_OWNER. Self-hosted and Local use byte-identical signed engine and DataPack payloads.

Community is free for personal, company and commercial use, including Local and Self-hosted deployment. The bundled universal signed Community License has no device binding, machine-code submission, activation server or manual approval. Reasonably display **Powered by Nora · PalEcho**. Commercial / Enterprise attribution removal is available through a separate license, including white-label / OEM authorization. SDK: Apache-2.0. Runtime and DataPack: Proprietary.
