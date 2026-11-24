# Security Policy

## Supported Versions

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `0.4.x` | Yes | Active clean-room research mainline (`Dev/schemas/`, `Dev/scripts/`, clean-room `.decomp` export) |

## Security & Clean-Room Boundaries

- **Zero Retail Media Distribution:** No copyrighted ROM images, `.nes`/`.fds`/`.prg`/`.chr`/`.s` binaries, extracted graphics/audio assets, or Ghidra `.gpr`/`.rep` databases are committed to Git, packaged in `Archive/`, or included in `.decomp` bundles.
- **Fail-Closed Media Verification:** Unpackers and verification scripts validate user-supplied `NES-ME-USA` media via SHA-256 checksums before processing and return structured errors when required local media is absent.
- **Path & Execution Isolation:** Tooling uses Python standard library modules with explicit `--data-dir` and `--log-dir` containment, offline synthetic fixtures, and zero `eval`/`exec` or shell-injected subprocess calls.
- **No Secrets or Private Paths in Repo:** API tokens, webhook URLs, local configuration files (`Dev/data/`), and personal filesystem paths are never committed or shipped in packages.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for suspected security vulnerabilities or accidental asset/path leakage.

1. Report privately via GitHub **Security Advisories** (`Report a vulnerability` on the repository Security tab).
2. Include the affected script, schema, or documentation path, version (`0.4.x`), reproduction steps, and expected vs. actual behavior.
3. Maintainers acknowledge reports within **72 hours** and coordinate a fix before public disclosure.
