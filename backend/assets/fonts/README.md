Fonts for the share cards the pipeline draws (`backend/helpers/share_cards.py`),
the same two the site uses:

- `inter-latin-wght-normal.woff2`: Inter (SIL Open Font License, see
  `Inter-LICENSE.txt`), the variable-weight Latin subset the site serves
  from `nginx/html/static/fonts/`. Everything else.
- `Nippo-Bold.otf`: Nippo by the Indian Type Foundry, from Fontshare, under the
  ITF Free Font License. Titles. **Not in the repository** (see below).

## Nippo

The ITF Free Font License lets this site self-host Nippo and draw images with
it, but not modify the font (subsetting or converting it counts) or make it
available through a public repository. So the files are git-ignored and
installed by hand, unmodified, wherever the site runs:

1. Download Nippo from <https://www.fontshare.com/fonts/nippo> and unzip it.
2. Copy, from the download, as they come:
   - the Bold OpenType file to `backend/assets/fonts/Nippo-Bold.otf` (the share
     cards; the worker image copies it in when it's built, so do this before
     `docker compose … up --build`);
   - the Bold WOFF2 webfont to `nginx/html/static/fonts/Nippo-Bold.woff2` (the
     site; nginx serves that folder directly, so no restart is needed).

   If a file's name differs, give the copy the name above: renaming the file
   doesn't change the font.

Without them, everything still works: the site's titles fall back to Inter
(`--font-display` in `app.css`), and the share cards draw their titles in Inter
Bold and log a warning. Tests and CI run that way.
