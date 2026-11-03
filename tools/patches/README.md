# Live patches not yet folded into the repo copies

Some live files are too large to push from the chat tools. Each script here rebuilds the live file byte-for-byte from
the repo copy. To fold one in: run it with `APP` pointed at a checkout, check the printed sha256[:16], commit the result,
then delete the script.

| Script | File | Repo copy sha256[:16] | Live sha256[:16] | Live since (UTC) |
|---|---|---|---|---|
| `nffeeds_v1.py` | `sync_newsfile_direct.py` | `d8fdc9a3c9ccad22` | `8103f2c34918f3ce` | 2026-11-03 14:57 |
| `nfstubloop_v1.py` (run after `nffeeds_v1.py`) | `sync_newsfile_direct.py` | `8103f2c34918f3ce` | `aa9011c31083a9cc` | 2026-11-03 17:06 |
| `wiretick_v1.py` (needs `wireticker.py` beside it; the repo root copy is the live file, `3bd6fccc92bf6d50`) | `sources/globenewswire_gnews.py` | `3e0bedacc9ffe072` | `d9fe99ea4493ab2c` | 2026-11-03 18:08 |
| | `sources/businesswire_gnews.py` | `e9adaa110f04e144` | `3adfb31b2fbd968a` | |
| | `sources/prnewswire_gnews.py` | `42d8e8ab244a24e2` | `f65cebc40700445f` | |
| | `sources/cnw_gnews.py` | `1c927c8081ace7e5` | `bf7f17e1f067460a` | |

Also not in the repo: `exchange_news.py` EXCH_OCRFB_V2 (live `1eab558e6b707eb5` since 2026-11-02 21:30 UTC); its
patcher is `mnt-relay` `payloads/pdfocr/patch_ocrfb2.py`.
