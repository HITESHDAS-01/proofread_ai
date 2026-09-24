# AI Proofreader — commercial readiness notes (internal, not shipped)

## License choice
**Proprietary free software** (see LICENSE). Why:
- You keep commercial control (no one can repackage/resell your app)
- End users free for personal & normal use
- BYOK model is explicit — no API cost on you
- Open source (MIT/Apache) would allow competitors to fork and sell; avoid unless intentional

## Distribution checklist
- [x] LICENSE
- [x] PRIVACY.md
- [x] BYOK messaging in UI
- [x] Unit tests (23+)
- [x] CI: test on push + build on tag `v*`
- [x] Inno Setup script: `installer\AIProofreader.iss`
- [x] Auto-update (GitHub Releases): Settings → update_repo `owner/repo`, auto-check on launch
- [ ] Code signing cert (~$100–200/yr) — DigiCert, Sectigo, SSL.com
- [ ] First tag: `git tag v1.0.0 && git push origin v1.0.0` → CI builds release
- [ ] Optional: install Inno Setup and run `iscc installer\AIProofreader.iss`

## Auto-update flow
1. Default repo: **HITESHDAS-01/proofread_ai** (`config.py` + `updater.py`)
2. Or override **Settings → Update source**
3. On launch (after ~4s) app hits GitHub `releases/latest`
4. If newer tag → dialog → download `.exe` → bat waits for exit → replace → restart
5. Needs a `.exe` asset on the release (CI already uploads it)
6. Code signing strongly recommended so SmartScreen doesn't scare users mid-update

## Publish updates
```bash
git tag v1.0.1
git push origin v1.0.1
```
CI runs tests → builds exe → creates GitHub Release with `.exe` asset → clients auto-update.

## Ship package contents
- AI_Proofreader.exe
- LICENSE
- PRIVACY.md
- (or built Setup exe from Inno)

## What NOT to ship
- `.env` with your API keys
- Source (unless intentional)
