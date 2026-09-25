# Windows x64 Local Edition

Target: Windows 11 x64.

Planned asset: `Nora-Setup-v1.1.1-Windows-x64-Experimental.exe`.

**Release withheld: no runnable Windows PE Runtime is available.** No EXE is published in v1.1.1-preview. Native 160-case validation, decision-affecting case count and clean-machine acceptance are NOT MEASURED. The macOS result does not establish Windows numerical behavior.

Any future package without native acceptance must be labeled **Experimental Preview**, for evaluation, testing and integration only. It must not be used for production nutrition decisions. Windows is not officially supported or production validated by this preview.

The intended experience is download EXE → install → launch. The installer must include the Runtime, encrypted DataPack, license verifier, necessary dependencies, CLI bridge, application directories, updater and uninstaller. Windows code signing is pending. Those installation steps and SmartScreen behavior have not been verified.

Community permits personal, company, commercial and local deployment for free with **Powered by Nora · PalEcho**. A separate Commercial / Enterprise authorization can remove attribution. See [licensing](licensing.md).
