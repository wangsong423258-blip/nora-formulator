# Contributing

Contributions cover client transport, types, schemas, CLI behavior, accessibility of documentation and integrations. Keep calculation services and data assets outside this repository.

Use artificial minimal inputs and mocked HTTP responses. Do not add real meal results, nutritional reference tables, service dumps, customer data, credentials or bulk fixtures. Do not add implementation details for calculation services to comments or documentation.

Use Node.js 22 or later. Run `node cli/nora.mjs --help` for a CLI smoke check. Runtime installation requires a separately supplied verified bundle; no runnable bundle is available in this preview. The publisher performs the contract and release-content checks before publication.

A file absent from PUBLIC_MANIFEST.json is denied, including hidden files. Review each added or modified file before updating its hash. Do not broaden scan exceptions to make a failed build pass. Exact license statements and the documented local loopback endpoint have narrowly reviewed line-hash exceptions.

Intentional contributions are provided under Apache-2.0. Maintainers must verify that contributors have the right to publish submitted material. Inclusion here does not license separately held services or data.
