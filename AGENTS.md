# Repository guidance

- Use uv for Python environments and dependency management; commit uv.lock.
- Keep new comments and documentation in English.
- Never commit browser cookies, tokens, signed URLs, personal filenames or account
  inventories. Store all live-session material under ignored `.local/`.
- Keep CLI commands read-only. Live verification must not download media, upload,
  delete, rename, import or mutate cloud objects without a direct user request.
- Use synthetic metadata in tests; never make network calls from unit tests.
- HTTP errors must omit credentials, query strings and full server payloads.
- Keep explicit endpoint allowlists and timeouts; do not retry mutations.
- Run the checks documented in README before committing.
- The upstream repository is public. Review staged content for private data
  before publishing; do not publish live verification output.
- CLI list/export operations hide API cursors and consume all pages by default.
  Preserve complete API object fields in raw exports; keep compact inventories
  available for existing offline plans. Recursive exports must retain membership
  when one file belongs to multiple containers.
