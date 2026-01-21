# Remaining Work for NEMF Review Tool

## Completed During This Session

✅ **Phase 4 & 5 Backend Implementation**
- Created `app/mo_api_client.py` with full MO API2 integration
- Added server endpoints for add-to-existing and create-new workflows
- Implemented field slip conflict detection (one-to-one relationship model)
- Created comprehensive documentation

✅ **Documentation**
- `FIELDSLIP_ANALYSIS.md` - Analysis of one-to-one vs many-to-many relationships
- `PHASE_4_5_IMPLEMENTATION.md` - Complete implementation guide with testing instructions
- Updated `DEPLOYMENT_PLAN.md` with Phase 4 & 5 status

## Remaining Work

### 1. UI Integration (High Priority)

**Add to review.html template:**

```javascript
// Phase 4: Add to Existing button and form
function showAddToExistingDialog() {
  // Prompt for observation ID
  // Validate observation exists
  // Submit to /api/mo/add_to_existing
  // Handle success/error
}

// Phase 5: Create New button
function showCreateNewDialog() {
  // Use current review form data
  // Submit to /api/mo/create_new
  // Handle success/error
}

// Success handler
function handleUploadSuccess(response) {
  // Show success message
  // Display links to MO observation and image
  // Mark image as uploaded
  // Navigate to next image
}

// Error handler with conflict resolution
function handleUploadError(error) {
  if (error.includes('already exists')) {
    // Show conflict resolution options
    // Link to existing observation
    // Suggest different field slip code
  } else {
    // Show generic error
  }
}
```

**UI Elements to Add:**
- "Upload to MO" button group with Phase 4/5 options
- Observation ID input field for Phase 4
- Validation indicators (API key status, required fields)
- Progress indicators during upload
- Success/error toast notifications
- Links to created MO observations

### 2. Testing (High Priority)

**Backend Testing:**
- [ ] Test MO API client with staging environment
- [ ] Verify all error cases (auth, not found, conflicts)
- [ ] Test field slip conflict scenarios
- [ ] Verify image upload and linking

**Integration Testing:**
- [ ] Test full Phase 4 workflow end-to-end
- [ ] Test full Phase 5 workflow end-to-end
- [ ] Test concurrent uploads from multiple users
- [ ] Verify review data is updated correctly

**User Acceptance Testing:**
- [ ] Have reviewers test with real NEMF data
- [ ] Collect feedback on workflow
- [ ] Identify edge cases

### 3. Deployment to DigitalOcean (Medium Priority)

**From Phase 1 (still pending):**
- [ ] Set up DigitalOcean droplet (Ubuntu 24.04, 2GB RAM)
- [ ] Install Python, Nginx, Gunicorn
- [ ] Configure systemd service
- [ ] Upload review data and images (1.6GB)
- [ ] Set up HTTPS with Let's Encrypt (optional for 2-week deployment)
- [ ] Test access from team

**Deployment Commands:**
```bash
# Upload images
rsync -avz --progress nemf-photos/unique/ user@server:/var/www/nemf-review/data/images/

# Upload data files
scp review_data.json all_*.json users.json user@server:/var/www/nemf-review/data/

# Deploy code
git push origin main
ssh user@server "cd /var/www/nemf-review && git pull && sudo systemctl restart nemf-review"
```

### 4. User Documentation (Medium Priority)

**Create user guide covering:**
- [ ] How to get MO API key
- [ ] How to configure API key in Settings
- [ ] When to use "Add to Existing" vs "Create New"
- [ ] How to resolve field slip conflicts
- [ ] How to find existing observations
- [ ] Best practices for review workflow

### 5. Field Slip Considerations (Low Priority - Future)

**Decision needed:** One-to-one vs many-to-many

**If many-to-many is needed:**
- Evaluate actual conflicts in NEMF data first
- Estimate migration effort (2-3 days)
- Plan implementation after initial deployment
- See `FIELDSLIP_ANALYSIS.md` for details

**For now:** Proceed with one-to-one relationship + conflict detection

### 6. Optional Enhancements (Future)

**Batch Operations:**
- Upload multiple images at once
- Create observations for all linked images
- Progress tracking

**Enhanced Validation:**
- Auto-detect duplicate specimens
- Suggest observation merging
- Validate location/name combinations

**Reporting:**
- Upload statistics per reviewer
- Field slip usage report
- Error/conflict report

## Quick Start for Next Session

1. **Test the backend:**
   ```bash
   cd /Users/nathan/src/mushroom-observer/projects/nemf-review
   python3 -m pytest app/mo_api_client.py  # If tests exist
   ```

2. **Start the server:**
   ```bash
   python3 app/server.py --port 5001 --data review_data.json
   ```

3. **Test the endpoints:**
   ```bash
   # Test Phase 4
   curl -u username:password -X POST http://localhost:5001/api/mo/add_to_existing \
     -H "Content-Type: application/json" \
     -d '{"filename":"IMG_6822.jpeg","observation_id":123456,"field_code":"TEST-001"}'

   # Test Phase 5
   curl -u username:password -X POST http://localhost:5001/api/mo/create_new \
     -H "Content-Type: application/json" \
     -d '{"filename":"IMG_6822.jpeg","field_code":"TEST-002","date":"2024-09-15"}'
   ```

4. **Add UI integration** to `templates/review.html`

## Priority Order

1. **Immediate:** UI integration for Phase 4 & 5
2. **High:** Backend testing with real MO API
3. **High:** User documentation and API key setup guide
4. **Medium:** Deploy to DigitalOcean
5. **Medium:** User acceptance testing
6. **Low:** Consider many-to-many field slips (after deployment)

## Notes

- Backend implementation is complete and ready for testing
- Field slip conflict handling follows conservative one-to-one model
- Can migrate to many-to-many later if needed (minimal risk)
- Focus on UI integration next for complete workflow
