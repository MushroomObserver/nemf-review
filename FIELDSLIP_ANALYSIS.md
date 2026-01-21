# FieldSlip Relationship Analysis

## Current State: Many FieldSlips → One Observation

**CORRECTION**: The current MO implementation actually has FieldSlips in a **many-to-one** relationship with Observations:

```ruby
class FieldSlip < AbstractModel
  belongs_to :observation  # Many field slips → one observation
  belongs_to :project
  belongs_to :user
end
```

### Example:
- Observation 533317 has multiple field slip records pointing to it
- Multiple FieldSlip records can share the same `observation_id`
- Field slip `code` is unique, but multiple codes can point to same observation

## The Real Problem: Duplicate Observations for Same Specimen

### NEMF Data Analysis

From `nemf-report` project duplicate analysis:
- **Total unique field slip codes:** 1,340
- **Codes with duplicates:** 653 (49%)
- **Total duplicate references:** 729

**Breakdown:**
- 582 codes appear 2 times (43%)
- 66 codes appear 3 times (5%)
- 5 codes appear 4 times (<1%)

### Root Cause

Users create observations in **both** Mushroom Observer and iNaturalist for the same physical specimen, then import iNat observations into MO, resulting in:

1. **Same field slip code** (e.g., "NEMF-12345")
2. **Multiple observations** (one from MO, one from iNat import)
3. **Different owners** (may not want observations merged)
4. **Need for deduplication** (but can't block imports)

### Current Limitation

The current relationship (many FieldSlips → one Observation) does **not** solve this problem because:
- Each FieldSlip record must have a unique `code`
- Can't create second FieldSlip with code "NEMF-12345" for a different observation
- Attempting to do so would violate unique constraint

## What We Actually Need: One FieldSlip → Many Observations

To properly model the real-world scenario:

```ruby
# One field slip code can reference multiple observations
# (same specimen, multiple records by different users/sources)

class FieldSlip
  has_many :field_slips_observations
  has_many :observations, through: :field_slips_observations
  # code is still unique, but now points to multiple observations
end

class Observation
  has_many :field_slips_observations
  has_many :field_slips, through: :field_slips_observations
end
```

### Why This Model Works

**Scenario:** Field slip "NEMF-12345" for *Amanita muscaria* collected on 2024-09-15

1. **User A** creates observation on MO → Links to NEMF-12345
2. **User A** also creates observation on iNat → Same specimen, same code
3. **Import** brings iNat observation into MO → Now two MO observations
4. **FieldSlip "NEMF-12345"** should link to both observations
5. **Project admin** can later review and decide:
   - Merge observations (same specimen, duplicate records)
   - Keep separate (data quality, different photos, ownership preferences)

**Current system cannot handle this** - second observation cannot link to "NEMF-12345"

## Database Schema Change Required

### Migration

```ruby
class ConvertFieldSlipsToManyToMany < ActiveRecord::Migration[7.2]
  def up
    # Create join table
    create_table :field_slips_observations do |t|
      t.references :field_slip, null: false, foreign_key: true
      t.references :observation, null: false, foreign_key: true
      t.timestamps
    end

    # Add unique index to prevent duplicate links
    add_index :field_slips_observations,
              [:field_slip_id, :observation_id],
              unique: true,
              name: 'index_field_slips_observations_unique'

    # Migrate existing data
    FieldSlip.where.not(observation_id: nil).find_each do |fs|
      FieldSlipsObservation.create!(
        field_slip_id: fs.id,
        observation_id: fs.observation_id
      )
    end

    # Remove old foreign key
    remove_column :field_slips, :observation_id
  end

  def down
    # Add back observation_id column
    add_reference :field_slips, :observation, foreign_key: true

    # Migrate back (keeping only first observation for each field slip)
    FieldSlipsObservation.group(:field_slip_id).minimum(:observation_id).each do |fs_id, obs_id|
      FieldSlip.find(fs_id).update!(observation_id: obs_id)
    end

    # Drop join table
    drop_table :field_slips_observations
  end
end
```

### Updated Models

```ruby
class FieldSlip < AbstractModel
  has_many :field_slips_observations, dependent: :destroy
  has_many :observations, through: :field_slips_observations
  belongs_to :project
  belongs_to :user

  validates :code, uniqueness: true, presence: true
end

class Observation < AbstractModel
  has_many :field_slips_observations, dependent: :destroy
  has_many :field_slips, through: :field_slips_observations
  # ... other associations
end

class FieldSlipsObservation < AbstractModel
  belongs_to :field_slip
  belongs_to :observation

  validates :observation_id, uniqueness: { scope: :field_slip_id }
end
```

## Impact on NEMF Review Tool

### Phase 4: Add to Existing Observation

**With many-to-many relationship:**

```python
# Check if field slip code already exists
field_slip = mo_api.get_field_slip_by_code(code)

if field_slip:
    # Field slip exists, check if already linked to this observation
    if observation_id in field_slip['observation_ids']:
        # Already linked, nothing to do
        return field_slip
    else:
        # Link to additional observation
        mo_api.link_field_slip_to_observation(field_slip['id'], observation_id)
        return field_slip
else:
    # Create new field slip and link to observation
    field_slip = mo_api.create_field_slip(code, project_id)
    mo_api.link_field_slip_to_observation(field_slip['id'], observation_id)
    return field_slip
```

**No blocking conflicts** - same field slip can link to multiple observations

### Phase 5: Create New Observation

**With many-to-many relationship:**

```python
# Check if field slip code already exists
field_slip = mo_api.get_field_slip_by_code(code)

if field_slip:
    # Warn about duplicates but allow creation
    print(f"Warning: Field slip {code} already linked to {len(field_slip['observation_ids'])} observation(s)")
    # Create observation anyway
    observation = mo_api.create_observation(...)
    # Link to existing field slip
    mo_api.link_field_slip_to_observation(field_slip['id'], observation['id'])
else:
    # Create new field slip
    field_slip = mo_api.create_field_slip(code, project_id)
    # Create observation
    observation = mo_api.create_observation(...)
    # Link them
    mo_api.link_field_slip_to_observation(field_slip['id'], observation['id'])
```

**Enables import workflow** - no blocking on duplicates

### UI Enhancements

**When field slip code already exists:**
1. Show warning: "This field slip code is already used by X observation(s)"
2. Display links to existing observations
3. Allow user to proceed or review existing observations
4. Flag for admin review/deduplication

## Implementation Recommendation

### Immediate (Pre-Deployment)

**Implement many-to-many relationship in MO core:**
- Required to handle NEMF duplicate imports
- Prevents blocking imports waiting for deduplication
- Enables proper tracking of duplicate observations

**Estimated effort:** 1-2 days
- Database migration
- Model updates
- API updates (FieldSlip API needs modification)
- Controller/view updates
- Tests

### Review Tool Changes

**Update `mo_api_client.py`:**
```python
def link_field_slip_to_observation(self, field_slip_id: int, observation_id: int):
    """Link a field slip to an observation (many-to-many)."""
    return self._request(
        'POST',
        f'/api2/field_slips/{field_slip_id}/link_observation',
        data={'observation': observation_id}
    )

def create_or_link_field_slip(self, code: str, observation_id: int, project_id: Optional[int] = None):
    """Create field slip or link existing one to observation."""
    existing = self.get_field_slip_by_code(code)

    if existing:
        # Check if already linked
        if observation_id in existing.get('observation_ids', []):
            return existing
        # Link to additional observation
        self.link_field_slip_to_observation(existing['id'], observation_id)
        return self.get_field_slip_by_code(code)  # Refresh

    # Create new
    field_slip = self.create_field_slip(code, project_id)
    self.link_field_slip_to_observation(field_slip['id'], observation_id)
    return field_slip
```

### Admin Deduplication Tool (Post-Deployment)

**Allow project admins to:**
1. View all observations linked to same field slip
2. Compare observations side-by-side
3. Merge observations (combine images, keep one record)
4. Unlink incorrect field slip associations
5. Flag user errors vs legitimate duplicates

## Migration Risks

### Low Risk
- Join table approach is standard Rails pattern
- Existing data migrates cleanly (one-to-many becomes many-to-many)
- Rollback is straightforward (keep first observation per field slip)

### Data Integrity
- No data loss during migration
- All existing FieldSlip→Observation links preserved
- New links can be added for duplicates

### API Compatibility
- GET endpoints: Return `observation_ids` array instead of single `observation_id`
- POST/PATCH: Accept multiple observations or use separate link endpoint
- Versioned API can maintain backward compatibility if needed

## Decision

**Implement many-to-many relationship before NEMF tool deployment:**

✅ **Required** for handling duplicate imports (49% of codes)
✅ **Prevents blocking** imports on deduplication
✅ **Low risk** - standard Rails pattern
✅ **Enables** proper duplicate tracking and admin review
✅ **Future-proof** - handles MO/iNat import workflow

**Alternative (blocking imports):** Not practical - would require resolving 653 duplicate codes before any imports proceed

## Timeline

1. **Week 1:** Implement many-to-many in MO core
   - Database migration
   - Model/API updates
   - Tests

2. **Week 2:** Update review tool
   - Update mo_api_client.py
   - Update server endpoints
   - Add duplicate warnings to UI

3. **Week 3:** Deploy and test
   - Import NEMF data
   - Track duplicates
   - Plan admin deduplication

4. **Future:** Admin deduplication tool
   - Review duplicate observations
   - Merge or confirm separate
   - Clean up user errors
