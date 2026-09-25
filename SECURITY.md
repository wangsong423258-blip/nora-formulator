# Security reporting

Do not put credentials, customer profiles, service responses or sensitive attachments in public issues or pull requests. Use GitHub's private vulnerability reporting when enabled. If unavailable, ask maintainers for a private reporting channel using only a nonsensitive request; keep vulnerability details private while waiting.

Never submit a working credential as a reproduction. Use artificial data and mocked transport. If a credential is exposed, its owner should revoke or rotate it through their provider. The client does not store credentials on disk, log request bodies, follow HTTP redirects or retry requests automatically.

Changes to release policy, manifests and publishing require review. Static checks supplement review and cannot prove the absence of every possible information leak. See [distribution security](docs/security.md).
