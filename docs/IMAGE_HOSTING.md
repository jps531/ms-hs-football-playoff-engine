# Image Hosting: Cloudinary

## Context

The frontend needs to display school logos and helmet images. Currently all image references in the DB are external URLs (MaxPreps-hosted). The existing schema already has hooks for managed images:
- `schools.overrides` JSONB → `display_logo` field surfaced in the `schools_effective` view
- `helmet_designs.image_left`, `image_right`, `photo` URL columns

The goal is to use Cloudinary as a self-controlled image store with predictable, overwriteable URL paths stored in those existing columns.

---

## Why Cloudinary

- **Named public IDs**: path is set by you on upload — `logos/primary/Taylorsville`. URL becomes `https://res.cloudinary.com/{cloud}/image/upload/logos/primary/Taylorsville.png`, forever, no UUIDs, fully overwriteable.
- **Free tier**: 25 credits/month (storage + bandwidth + transforms bundled). A few hundred school logos + helmet images is well within limits.
- **Best GUI**: Media Library has folder trees, drag-and-drop, bulk rename, search by tag.
- **Zero local server**: same SDK + credentials work identically in dev and prod.
- **On-the-fly transforms**: `w_64,h_64,c_fill` in the URL gives a thumbnail at no extra cost — useful for frontend list views.
- **Future upgrade**: Cloudflare R2 (10 GB free, zero egress) is a clean swap if scale grows — just update `CLOUDINARY_BASE_URL` env var.

---

## Finder Integration

**Free: rclone + macFUSE** (~20 min one-time setup)
```bash
brew install rclone
# install macFUSE from https://osxfuse.github.io/
rclone config  # configure with Cloudinary API credentials
rclone mount cloudinary:/ ~/CloudinaryDrive --vfs-cache-mode writes
```
Mounts as a Finder network drive; drag-and-drop works like any folder.

**Paid ($35 one-time): Mountain Duck** — native Finder mounting identical to iCloud Drive behavior.

---

## Folder Structure

```
logos/
  primary/         ← main school logo (standings, game cards)
  secondary/       ← alternate logo
  watermark/       ← transparent version for backgrounds
helmets/
  {school}/        ← e.g., helmets/Taylorsville/2024_white_left.png
  generic/         ← fallback image
```

---

## DB Integration

### Schema change
Add explicit `logo_override TEXT` column to `schools` (cleaner than JSONB for a first-class field):
```sql
ALTER TABLE schools ADD COLUMN logo_override TEXT;
```
Update `schools_effective` view:
```sql
COALESCE(s.logo_override, s.maxpreps_logo) AS display_logo
```

### URL storage convention
Store only the **path** in the DB; assemble the full URL from an env var:
```
DB value:    logos/primary/Taylorsville
Env var:     CLOUDINARY_BASE_URL=https://res.cloudinary.com/{cloud}/image/upload
Full URL:    {CLOUDINARY_BASE_URL}/logos/primary/Taylorsville.png
```
Swapping backends later (e.g., to R2) requires only a single env var change, no DB migration.

---

## Implementation Steps

1. **Create Cloudinary account** (free, ~5 min at cloudinary.com)
2. **Add env vars** to `.env`: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_BASE_URL`
3. **Install SDK**: `pip install cloudinary` → add to `requirements.txt`
4. **Upload helper** (`backend/helpers/image_helpers.py`): thin wrapper enforcing path convention + `overwrite=True`:
   ```python
   import cloudinary.uploader

   def upload_image(local_path: str, public_id: str) -> str:
       """Upload image and return the path stored in DB (not full URL)."""
       cloudinary.uploader.upload(
           local_path,
           public_id=public_id,
           overwrite=True,
           invalidate=True,
       )
       return public_id  # store this in the DB
   ```
5. **Schema migration**: `ALTER TABLE schools ADD COLUMN logo_override TEXT`; update `schools_effective` view
6. **Update API models**: `SchoolMetadataModel.display_logo` already exists — populate from new column via the view
7. **Finder mount**: one-time rclone + macFUSE setup
8. **Bulk logo import**: download from MaxPreps URLs → upload to `logos/primary/{school_name}` → update `logo_override` in DB

---

## Files to Modify

| File | Change |
|------|--------|
| `sql/init.sql` | Add `logo_override TEXT` to schools table; update `schools_effective` view |
| `backend/helpers/image_helpers.py` | New file — upload helper |
| `requirements.txt` | Add `cloudinary` |
| `.env.example` | Document Cloudinary env vars |
| API layer | No change needed — `display_logo` already flows through `SchoolMetadataModel` |

---

## Verification

- Upload test image via Cloudinary Media Library GUI → confirm predictable URL
- Overwrite same path → confirm URL unchanged, new image served
- Finder mount: drag image into `~/CloudinaryDrive/logos/primary/` → confirm it appears in Media Library
- DB round-trip: store path in `logo_override`, query via `schools_effective`, assemble full URL in API response
- Local dev: SDK calls work with same credentials as prod (no local server needed)
