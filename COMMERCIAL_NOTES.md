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
1. Default repo: **HITESHDAS-01/ai-proofreader-releases** (`config.py` + `updater.py`)
   - Source repo `HITESHDAS-01/proofread_ai` stays **private**; public downloads live in the
     releases repo (created 2026-09-25, has README + LICENSE stub + mirrored releases)
   - `load_settings()` migrates old `update_repo` values automatically
2. Or override **Settings → Update source**
3. On launch (after ~4s) app hits GitHub `releases/latest` (unauthenticated API)
4. If newer tag → dialog → download `.exe` → bat waits for exit → replace → restart
5. Needs a `.exe` asset on the release (CI already uploads it)
6. Code signing strongly recommended so SmartScreen doesn't scare users mid-update

## Release repos & CI publishing
- CI (`build.yml`) publishes releases to **both** repos on tag push:
  - source repo via `GITHUB_TOKEN`
  - public releases repo via `secrets.RELEASES_TOKEN`
- `RELEASES_TOKEN` = fine-grained PAT, single repo `ai-proofreader-releases`,
  Contents: Read & write → add with `gh secret set RELEASES_TOKEN`.
  Until it exists, CI skips the public-repo step; mirror releases manually with:
  `gh release create vTAG --repo HITESHDAS-01/ai-proofreader-releases --title vTAG --notes "..." dist/AI_Proofreader.exe LICENSE PRIVACY.md`
- `release: published` trigger removed — manual releases are no longer rebuilt/clobbered by CI
- CI builds (Python 3.11) are the slim ~17.5MB exes; local builds match after adding
  `excludes=["numpy", ...]` to `AI_Proofreader.spec` (numpy came from a Pillow hook, unused)

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
