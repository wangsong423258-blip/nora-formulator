# Linux x64 Self-hosted — Experimental Preview

[Download Runtime TAR.GZ](https://github.com/wangsong423258-blip/nora-formulator/releases/download/v1.1.1-preview/Nora-Runtime-v1.1.1-Linux-x64-Experimental.tar.gz) and verify its SHA256 against the Release checksums. Extract the entire archive and open a terminal in the extracted directory:

```sh
./cli/nora install
./cli/nora start
./cli/nora status
```

The native Runtime was built and tested on Ubuntu 24.04 x64. Older distributions and other architectures are not certified; see the archive's `docs/BUILD_COMPATIBILITY.json` for dynamic libraries and glibc requirements. No Desktop GUI, installer, Python environment, compiler or source checkout is required.

The Runtime automatically installs and verifies the included encrypted/signed DataPack and universal signed Community License. Companies and individuals can run it on their own Linux x64 hosts or servers. Core calculation does not depend on PalEcho cloud services.

For a dedicated persistent instance directory, pass `--home` with the same absolute path to every CLI command. Your trusted backend can use the public SDK with the private `connection.json` generated in that instance directory. Keep the token private; do not expose the loopback adapter directly to the internet. DataPack and License remain in the managed `releases` directory. `./cli/nora stop` stops the Runtime; `./cli/nora uninstall` removes the installation. Updates require a newer compatible signed bundle via `./cli/nora update --bundle NEW/runtime`.

Existing native CI passed Runtime start, DataPack load, Community License verification, real formulation smoke, offline operation, restart, install/uninstall/reinstall and backend integration. Automatic service registration and reboot recovery were not tested. Valid update and rollback were not run because no newer signed candidate was available. The archive is the unchanged CI candidate; its bundled candidate wording predates this public Experimental release approval.

## Numerical status

Linux x64 is **Experimental Self-hosted Preview**, with **no production support**. The existing Ubuntu 24.04 x64 native 160-case audit has 61 exact matches, 96 internal numeric differences, 1 display-equivalent result and 2 user-affecting differences: **158/160 user business results are equivalent; one case changes ingredient gram allocation and one case has a Solver timeout**. The timeout is included in the two user-affecting cases. Use for evaluation, testing and integration only, not formal production nutrition decisions. No numerical regression was rerun for this publication.

## Licensing

Community is free for personal, company and commercial use, including Self-hosted deployment. No device binding or manual approval is required. Reasonably display **Powered by Nora · PalEcho**. Commercial / Enterprise attribution removal requires separate authorization. SDK: Apache-2.0. Runtime and DataPack: Proprietary. [Licensing](licensing.md).
