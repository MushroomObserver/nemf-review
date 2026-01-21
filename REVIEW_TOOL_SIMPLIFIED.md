# NEMF Review Tool - Simplified Implementation

## Relationship-Agnostic Approach

The review tool works with **either** the current many-to-one or future many-to-many relationship. It focuses on its core responsibility: associating images with observations.

---

## Core Workflow

### 1. Display Candidate Observations

**For image with field slip code "NEMF-12345":**

```python
# Find all observations that reference this field slip code
candidates = []

# Search via field slip records
field_slip = mo_api.get_field_slip_by_code("NEMF-12345")
if field_slip:
    # Current system: one observation
    # Many-to-many: multiple observations
    observation_ids = field_slip.get('observation_ids', [field_slip.get('observation_id')])
    for obs_id in observation_ids:
        candidates.append(mo_api.get_observation(obs_id))

# Also search observation notes for this code
notes_matches = mo_api.search_observations(notes_has="NEMF-12345")
candidates.extend(notes_matches)

# Show to reviewer
display_candidates(candidates, primary=True)
```

**UI shows:**
```
Image: IMG_6822.jpeg
Field slip code found: NEMF-12345

Observations using this code:
⭐ #111111 - Amanita muscaria - 2024-09-15 - Mary [View] [Select]
⭐ #222222 - Amanita muscaria - 2024-09-15 - Mary (iNat) [View] [Select]

Or: [Specify different observation ID] [Create new observation]
```

### 2. User Selects Target Observation

**Three paths:**

**A. Select existing candidate observation**
```python
chosen_observation_id = 111111  # From candidate list
```

**B. Specify different observation ID**
```python
chosen_observation_id = 333333  # User enters manually
```

**C. Create new observation**
```python
# User fills form with name, date, location
chosen_observation_id = create_new_observation(...)
```

### 3. Add Image to Observation

```python
# Upload image
image_id = mo_api.upload_image(image_path, ...)

# Link to observation
mo_api.add_image_to_observation(chosen_observation_id, image_id)

# Update observation notes to include field slip code
mo_api.update_observation_notes(chosen_observation_id, f"Field slip: {field_slip_code}")
```

### 4. Handle Field Slip Record

**Simplified logic - works with any relationship:**

```python
field_slip_code = "NEMF-12345"
chosen_observation_id = 111111

# Check if field slip exists
existing_field_slip = mo_api.get_field_slip_by_code(field_slip_code)

if existing_field_slip:
    # Field slip exists - DO NOTHING to it
    # (Many-to-many system will auto-link via observation notes)

    # Alert user if adding to different observation
    linked_obs_ids = existing_field_slip.get('observation_ids', [existing_field_slip.get('observation_id')])

    if chosen_observation_id not in linked_obs_ids:
        show_alert(
            f"⚠️ Field slip {field_slip_code} exists but is linked to "
            f"observation(s) {linked_obs_ids}. You are adding this image "
            f"to observation {chosen_observation_id}. Proceed?"
        )
else:
    # Field slip doesn't exist - create it
    mo_api.create_field_slip(
        code=field_slip_code,
        observation_id=chosen_observation_id,
        project_id=project_id
    )
```

**Key principle: Review tool never modifies existing field slip records**

---

## Alert Logic

### When to Alert

**Alert if:**
1. Field slip exists
2. Image being added to different observation than field slip's observation(s)

**Alert message:**
```
⚠️ Field Slip Mismatch

Field slip "NEMF-12345" is already linked to:
  • Observation #111111 - Amanita muscaria - 2024-09-15 - Mary

You are adding this image to:
  • Observation #222222 - Amanita muscaria - 2024-09-15 - Mary (iNat)

This might be:
  ✓ Correct - Same specimen, duplicate observations (iNat import)
  ✗ Error - Wrong field slip code or wrong observation

[Proceed] [Cancel] [View Observations]
```

### Smart Alerts (Optional Enhancement)

**Detect likely errors:**
```python
def should_alert_error(existing_obs, target_obs, image_data):
    """Alert if likely user error vs legitimate duplicate."""

    # Same name, date, location → likely duplicate (iNat import)
    if (existing_obs.name == target_obs.name and
        existing_obs.date == target_obs.date and
        existing_obs.location_similar(target_obs.location)):
        return False  # Don't alert, likely legitimate duplicate

    # Different species → likely error
    if existing_obs.name != target_obs.name:
        return True

    # Different date (>7 days) → might be error
    if abs(existing_obs.date - target_obs.date).days > 7:
        return True

    # Different location (>10km) → might be error
    if existing_obs.location_distance(target_obs.location) > 10:
        return True

    return False
```

---

## API Calls Summary

### Required Endpoints

**1. GET /api2/field_slips?code=NEMF-12345**
```json
{
  "results": [{
    "id": 123,
    "code": "NEMF-12345",
    "observation_id": 111111,     // Current system
    "observation_ids": [111111, 222222],  // Many-to-many system
    "project_id": 42
  }]
}
```

**2. GET /api2/observations?notes_has=NEMF-12345**
```json
{
  "results": [
    {"id": 111111, "name": "Amanita muscaria", ...},
    {"id": 222222, "name": "Amanita muscaria", ...}
  ]
}
```

**3. POST /api2/images**
```json
{
  "upload": "<file>",
  "copyright_holder": "Mary",
  "notes": "Field slip: NEMF-12345"
}
```

**4. PATCH /api2/observations/:id**
```json
{
  "set_notes": "Field slip: NEMF-12345\n\n<existing notes>"
}
```

**5. POST /api2/field_slips**
```json
{
  "code": "NEMF-12345",
  "observation": 111111,
  "project": 42
}
```

**6. Optional (many-to-many): POST /api2/field_slips/:id/link_observation**
```json
{
  "observation": 222222
}
```

---

## Implementation Status

### Completed ✅

1. **MO API Client** (`mo_api_client.py`)
   - Upload images
   - Create observations
   - Create field slips
   - Get field slips by code
   - Error handling

2. **Server Endpoints** (`server.py`)
   - `/api/mo/add_to_existing` - Add image to observation
   - `/api/mo/create_new` - Create new observation
   - Field slip creation logic

3. **Documentation**
   - Relationship analysis
   - Implementation guide
   - Testing guide

### Needs Update 🔄

**Simplify field slip handling:**

```python
# Current (complex conflict detection)
if existing:
    if existing['observation_id'] == target_observation_id:
        return existing
    else:
        raise ConflictError(...)

# Simplified (relationship-agnostic)
if existing:
    # Don't modify existing field slip
    # Alert if adding to different observation
    if target_observation_id not in get_observation_ids(existing):
        alert_user(...)
    return existing
else:
    return create_field_slip(...)
```

### To Do 📋

1. **UI Integration**
   - Show candidate observations from field slip codes
   - Display alert when field slip mismatch detected
   - Add "Proceed anyway" / "Cancel" / "Review observations" options

2. **Testing**
   - Test with current many-to-one relationship
   - Verify alerts work correctly
   - Test field slip creation

3. **Documentation**
   - User guide for handling alerts
   - Decision tree: when to proceed vs cancel

---

## Relationship-Specific Behavior

### With Current (Many→One)

**Creating field slip with existing code:**
- API returns 409 Conflict ❌
- Review tool cannot auto-link to second observation
- User must manually resolve

**Alert frequency:**
- High - alerts whenever field slip exists for different observation

**Workflow friction:**
- Medium - requires manual intervention for duplicates

### With Many-to-Many

**Creating field slip with existing code:**
- API links to additional observation ✅
- Review tool proceeds automatically
- User sees info message only

**Alert frequency:**
- Low - only alerts for likely errors (different species, date, location)

**Workflow friction:**
- Low - duplicates handled automatically

---

## Recommendation

**Keep review tool simple:**
1. Find candidate observations using field slip codes ✅
2. Let user choose target observation ✅
3. Add image to chosen observation ✅
4. Handle field slip creation/linking ✅
5. Alert on potential mismatches ✅
6. Never modify existing field slip records ✅

**Works with either relationship model** - team can decide on MO core changes independently.

---

## Next Steps

1. **Review team discussion** - Many-to-many vs current relationship
2. **Simplify mo_api_client.py** - Remove complex conflict detection
3. **Update server endpoints** - Use simplified field slip handling
4. **Add UI** - Candidate observations display and alerts
5. **Test** - Verify works with current MO instance
6. **Deploy** - Review tool ready for use

**Timeline:** UI integration 2-3 days, testing 1-2 days, deploy 1 day
