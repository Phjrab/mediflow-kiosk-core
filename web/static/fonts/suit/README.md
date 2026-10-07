# SUIT Variable — official local asset

- Upstream: https://github.com/sun-typeface/SUIT
- Release: v2.0.5 (2024-07-24), https://github.com/sun-typeface/SUIT/releases/tag/v2.0.5
- Download: https://github.com/sun-typeface/SUIT/releases/download/v2.0.5/SUIT-Variable-woff2.zip
- WOFF2 SHA-256: `aa894a204d5a6fbae259dac6868d350cbd373a390caee0313f92946af741df23`
- License: SIL Open Font License 1.1; copyright SUNN, reserved font name SUIT. See LICENSE.
- Unmodified upstream WOFF2, LICENSE and SUIT-Variable.css are preserved here.
- Internal name table: `Version 2.040;Glyphs 3.2.3 (3260)`; release tag and internal version differ.
- Variable axis: `wght` 100–900 (default 100); CSS registers the whole range and explicitly requests UI weights 400–700.
- 2,933 Unicode mappings. All requested Korean/Latin/date specimens are covered. This is the official full file, not universal Unicode coverage: Japanese, Chinese and some Vietnamese characters need system fallback.
- The official CSS has no unicode-range. No subset, conversion, renamed font or synthetic weight was added.
- Runtime registration is in `../../css/mediflow-tokens.css`: family `SUIT Variable`, normal style, 100–900, swap. Relative URL resolves to the same-origin static asset; no font CDN or preload.

The upstream name table calls the default instance “SUIT Variable Thin”. Chromium CDP may report that family name while showing `SUITVariable-Regular` / `SUITVariable-Bold` postscript instances. The CSS family is deliberately registered as the official `SUIT Variable` name.
