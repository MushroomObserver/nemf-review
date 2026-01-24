# NEMF Review Tool - Quick Reference

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` / `a` | Approve image |
| `m` | Already on MO |
| `d` | Exclude |
| `s` / `n` / `→` | Next unreviewed |
| `p` / `←` | Back |
| `j` | Jump to image |
| `f` | Focus field code |
| `l` | Link image |
| `1-5` | NEMF dates (Wed-Sun) |
| `z` | Zoom |
| `Esc` | Close modal |

## Workflow Cheat Sheet

### Single Image Upload
1. Fill all required fields (Field Code, Date, Location, Name)
2. "Create New Observation" → Upload
3. Auto-advances to next

### Multiple Photos (Same Specimen)
1. Fill required fields on main image
2. Link related images
3. "Create New Observation" → Upload all
4. Auto-advances to next

### Add to Existing Observation
1. Fill required fields
2. "Add to Existing Observation"
3. Enter Observation ID → Upload
4. Auto-advances to next

### Already Uploaded
1. Enter Field Code only
2. "Already on MO"
3. Enter Observation or Image ID → Verify
4. Auto-advances to next

### Exclude Image
1. Click "Exclude" or press `d`
2. Auto-advances to next

## Required Fields

- **Field Code**: NEMF-##### (unique)
- **Date**: Select from dropdown or custom
- **Location**: Autocomplete from MO (must select)
- **Name**: Autocomplete from MO (must select)
- **Notes**: Optional

## Status Values

- **None**: Unreviewed
- **Approved**: Reviewed, ready for upload
- **Corrected**: Reviewed with corrections
- **Already on MO**: Exists on MO
- **Excluded**: Not suitable

**Resolved**: Image with status `approved`, `corrected`, `already_on_mo`, `excluded`, or with `mo_observation_id`

## Claims

- **Auto-claimed**: When you load image for review
- **Duration**: 5 minutes, auto-refreshed
- **View-only**: Back/Forward/Jump don't claim
- **Disabled**: Actions/fields disabled when claimed by others
- **Released**: Auto-released when navigating away

## Navigation

- **Next Unreviewed**: Shows highest priority unreviewed image
- **Back/Forward**: Navigate your viewing history (view-only)
- **Jump**: Go to specific position number
- **Peek**: Click adjacent images (no claim)

## Linking

- Click "Link Adjacent Image" or press `l`
- Select images from peek strip
- Linked images get green border
- All linked images upload together
- Unlink: Click linked image → "Unlink"

## Priority Order

1. Priority class (issues flagged)
2. Location priority
3. Has specific issues

Next Unreviewed automatically follows this order.

## Tips

- Use keyboard shortcuts for speed
- Press `f` then Tab through fields
- Link all related images BEFORE uploading
- Check extracted data - OCR may be wrong
- Field code must be unique
- Autocomplete requires 2+ characters
- After upload, auto-advances to next unreviewed

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't edit | Claimed by someone else → Next Unreviewed |
| Autocomplete empty | Type 2+ chars, try different terms |
| Upload failed | Check all required fields filled |
| Lost claim | Someone else claimed it → Next Unreviewed |
| Linked wrong image | Click it → Unlink (before upload) |
| Wrong date selected | Click "Other" for custom date |

## Phase 4 vs Phase 5

- **Phase 4**: Add to EXISTING observation (need Obs ID)
- **Phase 5**: CREATE NEW observation (uploads linked images)
