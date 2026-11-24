# Contributing

Contributions are welcome, including bug reports, documentation improvements, format findings, and pull requests.

## Ways to Contribute

- **Bug Reports:** Open an issue with your OS, Python version, command run, and relevant output.
- **Pull Requests:** Keep changes focused on a single fix or feature, and include unit tests for new behavior.
- **Documentation:** Improvements to clarity, `UNROM` hardware notes, and binary format specifications are always appreciated.

## Dev Setup & Running Checks

```powershell
git clone https://github.com/StreamResearch/IronFrame-OuterFortress-Cart-01-Decomp.git
cd IronFrame-OuterFortress-Cart-01-Decomp
python -B -c "import sys; sys.path.insert(0, 'Dev/scripts'); import asm6502_d5; raw, org, _ = asm6502_d5.assemble_text('.org 0xC000\nLDA #0x01\nSTA 0x00\nRTS\n'); print(len(asm6502_d5.OPCODES), len(raw), hex(org))"
```

Run all 25 offline unit tests under `Dev/scripts/tests/` with:

```powershell
python -B -m unittest discover -s Dev/scripts/tests -v
```

## Pull Request Checklist

- [ ] All Python unit tests and clean-room schema checks pass with zero warnings.
- [ ] Scripts keep functions focused and modular without adding hardcoded machine paths.
- [ ] Documentation updates use repo-relative links (never local filesystem URIs).
- [ ] User-facing changes are noted in `CHANGELOG.md` under `[Unreleased]`.

## Clean-Room Rules

- **No Copyrighted Material:** Never commit or attach retail ROM images, `.nes`/`.prg`/`.chr`/`.s` payloads, extracted graphics or audio, or Ghidra `.gpr`/`.rep` databases.
- **No Retail Code or Strings:** Do not paste decompiled retail game function bodies, raw disassembly listings, or copyrighted game text into issues, pull requests, or tracked scripts.
- **Security & Leak Reports:** See [SECURITY.md](SECURITY.md) for private reporting.
