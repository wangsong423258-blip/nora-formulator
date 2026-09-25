# Local and self-hosted integration

Install a downloaded Mac Community Preview package and run its native CLI:

```sh
./nora install
./nora start
./nora status
```

The included Community License and DataPack are verified automatically. No `enroll`, device grant, registration or manual approval is needed. The default home is the current user's .nora directory; use --home DIR consistently for a dedicated installation. The connection.json file in that directory contains the local endpoint and access token. Read it only in your trusted backend. Never expose it in browser code.

The public Node.js SDK requires Node.js 22+; the bundled native CLI and Runtime do not. Initialize NoraClient with the protected connection object and call an operation from the 96-operation [Canonical v1 contract](contract.md). The HTTP adapter is an integration layer; the engine and its data run on your host without a PalEcho cloud calculation service.

Use `./nora stop` to stop, `./nora update --bundle /path/to/new/runtime` for a newer signed bundle, and `./nora uninstall` to remove an authenticated dedicated installation. An invalid update is rejected or rolled back to the previous installation pointer. A valid new-version upgrade has not been claimed solely from this 1.1.1 packaging run.

For developer use, the public Node CLI also accepts `node cli/nora.mjs install --bundle DIR --home DIR`. Its release trust pins verify this Preview's publisher signature. A separately issued Commercial / Enterprise authorization may use `license import FILE --grant FILE`; those additional issuance steps do not apply to the included Community license.

Windows packages remain pending. Linux and macOS Intel are outside Nora v1 scope.
