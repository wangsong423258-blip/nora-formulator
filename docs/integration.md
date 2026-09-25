# Local integration

Applications call the SDK, which sends Canonical v1 requests to Nora Local Runtime. All formulation calculation happens locally. The public SDK contains transport and interface types only.

Use the owner-readable connection file produced by the Runtime to supply `baseUrl` and `token`. The CLI reads `NORA_CONNECTION_FILE`, or the installation's `connection.json`; existing `NORA_API_URL` and `NORA_API_TOKEN` configuration remains supported. A bearer credential authorizes one local owner and is not a license. Protect it as an application credential.

`client.call(operationId, options)` retains all 96 Canonical v1 operations. `client.runtimeStatus()` returns Runtime version, API version, license edition, offline availability and attribution obligation. Errors expose stable codes, never data files or execution details. Responses are returned without numeric transformation.

The Runtime listens only on loopback, uses in-memory session state, and rejects browser Origin headers by default. Desktop clients can call directly. Browser products should use a trusted local application backend to authenticate calls and render results. Restarting the Runtime clears its in-memory session state. Persistent state and multi-tenant network operation require separate future design and validation.

`nora install --bundle DIR` accepts only a signed, platform-compatible distribution with no extra files and never overwrites an existing home. `nora enroll` creates a device identity in system credential storage; use `--provider passphrase` only when explicitly choosing the portable encrypted fallback. Import a publisher-signed license and device grant using `nora license import FILE --grant FILE`. `nora start`, `nora stop` and `nora status` manage the local service. `nora update --bundle DIR` verifies a newer signed distribution, checks compatibility and restores the previous pointer if activation fails. Production publisher pins and official signatures remain pending; the SDK refuses untrusted bundles.

The pre-signed Community license may be imported entirely offline. Individual users must not manufacture a PalEcho signature. A separate signed Commercial / Enterprise license is required to remove attribution. The Apache-2.0 SDK license alone does not authorize that removal.

Runtime status retains the `attribution` language object and may additionally return `attribution_text`. Community requires attribution; a verified Commercial license removes the obligation without reducing or changing calculation capabilities.

Updates that introduce a newly authorized data version can use
`nora update --bundle <signed-directory> --license <signed-license> --grant <signed-device-grant>`.
The installer validates compatibility and restores the prior release and entitlement
if activation fails. Encrypted passphrase storage can use an inherited `--unlock-fd`
for local automation; never put an unlock secret in arguments or configuration.
