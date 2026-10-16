Fonts for the share cards the pipeline draws (`backend/helpers/share_cards.py`),
the same two the site uses:

- `Nippo-Bold.otf`: Nippo by the Indian Type Foundry, from Fontshare
  (ITF Free Font License, free for commercial use). Titles. The site serves a
  Latin subset of it as `nginx/html/static/fonts/nippo-bold.woff2`, made with
  `pyftsubset Nippo-Bold.otf --unicodes="U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD" --flavor=woff2 --layout-features='*'`
  (fontTools + brotli).
- `inter-latin-wght-normal.woff2`: Inter (SIL Open Font License, see
  `Inter-LICENSE.txt`), the variable-weight Latin subset the site serves
  from `nginx/html/static/fonts/`. Everything else.
