# NEMF Review Tool - User Guide

Note: This document was initially generated using Claude Code and may be inaccurate. Overall I believe it will helpful. I have read through it briefly and fixed a few obvious inaccuracies, but I expect there are more issues. Let me know if you run into anything that does work as documented or if there other issues you encounter with this document. -Natha

## Table of Contents

- [Introduction](#introduction)
- [Getting Started](#getting-started)
- [Understanding the Interface](#understanding-the-interface)
- [Review Workflow](#review-workflow)
- [Image Claiming System](#image-claiming-system)
- [Data Entry](#data-entry)
- [Linking Images](#linking-images)
- [Upload Workflows](#upload-workflows)
- [Navigation](#navigation)
- [Tips and Best Practices](#tips-and-best-practices)
- [Troubleshooting](#troubleshooting)

---

## Introduction

The NEMF Review Tool is a web-based application for reviewing and uploading large sets of photos from the NEMF 2025 foray to Mushroom Observer. Most images are expected to include images of an MO Field Slip. The tool focuses on four key pieces of information:
- Field Slip Code
- Collection Location
- Collection Date
- Initial ID

Much of this data has already been automatically extracted, but all the data needs to be reviewed.

The tool helps multiple reviewers efficiently process hundreds of photos by:

- Allowing reviewers to correct and validate the extracted data
- Preventing conflicts when multiple reviewers work simultaneously
- Uploading observations and images to Mushroom Observer
- Tracking progress and review status


## Getting Started

### Getting Credentials

Post a message in the #nemf MO Slack channel requesting an account.  One of the admins will help you get your credentials registered on the server.

### Logging In

1. Go to http://142.93.176.28/.  Note this site is not "secure" according to most web browsers.  It is only expected to be available until January 31, 2026 and there really aren't any serious security concerns. However, it is strongly recommended that you use a randomly generated password that you do not use for any other purpose. One of the admins can help you with this.
2. Enter your username and password (HTTP Basic Auth)
3. You'll be taken to the main review interface

### First Steps

When you first log in, you'll see:
- The first unreviewed image at the top
- Extracted field slip data in the "EXTRACTED DATA" panel
- Edit fields in the "REVIEW / CORRECTIONS" panel that should initially have the extracted field slip data
- Summary statistics showing review progress

## Understanding the Interface

### Main Sections

**Image Display Area**
- Large image preview at the top
- Click image zoom/view full size
- Adjacent image strip below showing linked or nearby images
- Click adjacent images to preview (peek) without claiming them
- Image strip is scrollable

**Summary Panel** (top right)
- Total images in the review set
- Number of images reviewed
- Number excluded
- Number pending review

**Extracted Data Panel** (middle left)
- Shows OCR-extracted field slip data
- Includes: field code, date, location, species name, notes
- This is READ-ONLY - use for reference when filling review data

**Review / Corrections Panel** (middle right)
- Where you enter corrected/validated data
- All fields except Notes are required for upload
- Changes here override the extracted data

**Claim Status** (below image)
- Shows who has claimed the current image
- Green checkmark = you have claimed it
- Red warning = someone else is reviewing it
- When someone else has claimed an image, action buttons and form fields are disabled

**Navigation Controls** (bottom)
- Back/Forward buttons to navigate your viewing history
- "Jump to Image" to go to a specific position
- "Next Unreviewed" to skip to next pending image

### Priority System

Images are automatically sorted by priority:
1. **Priority class**: Images marked with issues (red flags) come first
2. **Location priority**: Within each priority class, sorted by location
3. **Issue flags**: Images with specific problems (e.g., missing data, unclear text)

The tool automatically shows you the highest-priority unreviewed image.

## Review Workflow

### Basic Review Process

1. **View the image** - Examine the field slip photo
2. **Check extracted data** - Review what the OCR system extracted
3. **Fill in review fields** - Enter correct data in Review/Corrections panel:
   - Field Code (e.g., NEMF-12345)
   - Date (select from dropdown or enter custom date)
   - Location (use autocomplete to find MO location)
   - Name/Species (use autocomplete to find MO name)
   - Notes (optional, any additional observations)
4. **Link related images** (if applicable) - See [Linking Images](#linking-images)
5. **Choose action**:
   - **Already on MO** - Image already uploaded, mark as resolved
   - **Add to Existing** - Add to an existing observation on MO
   - **Create New** - Create a new observation with this image
   - **Exclude** - Mark image as not suitable for upload

### Review Status Values

- **None** (unreviewed) - Not yet reviewed
- **Approved** - Reviewed and ready for upload
- **Corrected** - Reviewed with corrections applied
- **Already on MO** - Already exists on Mushroom Observer
- **Excluded** - Not suitable for upload

An image is considered "resolved" when it has status `approved`, `corrected`, `already_on_mo`, or `excluded`, OR when it has been uploaded (has an `mo_observation_id`).

## Image Claiming System

### How Claims Work

To prevent multiple reviewers from editing the same image simultaneously, the tool uses a "soft lock" claiming system:

**Claiming**
- When you load an image for review (not just peeking), you automatically claim it
- Your claim lasts for 5 minutes and is refreshed automatically while you work
- Other reviewers will see the image is claimed and cannot edit it

**Viewing vs. Editing**
- You can VIEW any image using Back/Forward/Jump navigation
- You can only EDIT images that you have claimed or that are unclaimed
- When viewing someone else's claimed image:
  - Action buttons are disabled
  - Form fields are disabled
  - You can see the current state but cannot make changes

**Claim Expiration**
- Claims automatically expire after 5 minutes of inactivity
- While working on an image, heartbeats keep your claim alive
- If you navigate away, your claim is released
- Expired claims allow other reviewers to claim the image

**Claim Conflicts**
- If someone else claims an image while you're working on it, you'll see a warning
- You cannot submit changes for an image claimed by someone else
- Use "Next Unreviewed" to find another image to work on

## Data Entry

### Required Fields

All fields except Notes are required for uploading to Mushroom Observer:

**Field Code**
- Format: `NEMF-#####` (e.g., NEMF-12345)
- Must be unique for each collection
- Used to create field slips on MO

**Date**
- Select from dropdown (Wednesday-Sunday of NEMF 2025)
- Or click "Other" to enter a custom date
- Format: YYYY-MM-DD

**Location**
- Type to search MO locations (autocomplete)
- Select from dropdown
- If location doesn't exist on MO, you may need to create it first
- Shows both location name and ID when selected

**Name/Species**
- Type to search MO names (autocomplete)
- Select from dropdown
- Can be genus-level or species-level
- Shows scientific name and common name

**Notes** (optional)
- Free-form text
- Any additional observations
- Habitat, substrate, abundance, etc.

### Using Autocomplete

Both Location and Name fields support autocomplete:

1. Start typing (minimum 2 characters)
2. Wait for dropdown to appear with matches
3. Use arrow keys or mouse to select
4. Press Enter or click to choose
5. The selected ID is stored automatically

The autocomplete searches MO's database of locations and names.

## Linking Images

### Why Link Images?

Often multiple photos are taken of the same specimen (overview, closeup, gills, etc.). Linking these images:
- Groups them together for upload
- Ensures they're added to the same observation
- Propagates review data to all linked images
- Saves time by not re-entering data

### How to Link

1. Review the main image and fill in data
2. Click "Link Adjacent Image"
3. Select the image(s) to link from the peek strip
4. Linked images show with a green border and "LINKED" badge
5. When you submit or upload, all linked images are included

### What Gets Propagated

When you link images and submit/upload:
- Field code
- Date
- Location (name and ID)
- Species name (name and ID)
- Notes
- Status
- MO observation ID (when uploaded)

All linked images get marked as `approved` or the same status as the main image.

### Unlinking

If you linked the wrong image:
1. Click on the linked image in the peek strip
2. Click "Unlink" button
3. The image is removed from the link group

## Upload Workflows

### Already on MO

Use this when the image has already been uploaded to Mushroom Observer:

1. Fill in the Field Code (required)
2. Click "Already on MO"
3. Enter the MO Observation ID or Image ID
4. Tool verifies the ID exists on MO
5. Image is marked as `already_on_mo` and you advance to next unreviewed

**ID Types**
- **Observation ID**: Full observation number (e.g., 624466)
- **Image ID**: Just the image number (if you know it)

### Add to Existing Observation

Use this when you want to add this image to an existing observation on MO:

1. Fill in all required fields (Field Code, Date, Location, Name)
2. Click "Add to Existing Observation"
3. Modal opens for MO upload
4. Enter the **Observation ID** to add to
5. Click "Add to Observation"
6. Tool uploads image to MO and adds it to that observation
7. Creates/links field slip to the observation
8. Shows success status with links to view on MO
9. Automatically advances to next unreviewed image

### Create New Observation

Use this to create a brand new observation on MO with this image:

1. Fill in all required fields (Field Code, Date, Location, Name)
2. Link any related images (optional)
3. Click "Create New Observation"
4. Modal opens for MO upload
5. Click "Create Observation"
6. Tool creates new observation on MO with all linked images
7. Creates field slip for the observation
8. Shows success status with links to view on MO
9. Automatically advances to next unreviewed image

### Exclude

Use this to mark an image as not suitable for upload:

1. Click "Exclude"
2. Image is marked as `excluded`
3. You advance to next unreviewed image

**When to exclude**
- Photo is too blurry
- Field slip is illegible
- Duplicate image
- Non-mushroom content

## Navigation

### Navigation Modes

The tool provides several ways to navigate:

**Next Unreviewed** (Primary)
- Click "Next Unreviewed"
- Jumps to the highest-priority unreviewed image
- Skips images that are resolved or claimed by others
- This is your main navigation method during review

**Back/Forward** (History)
- Click "Back" to go to previous image in your viewing history
- Click "Forward" to go forward in your history
- Does NOT claim images (view-only unless unclaimed)
- Useful for double-checking previous work

**Jump to Image**
- Click "Jump"
- Enter image name
- Goes directly to that image
- Does NOT claim the image

**Peek** (Adjacent Images)
- Click any image in the adjacent strip
- Opens preview without claiming
- Useful for inspecting before linking
- Does not add to view history

### After Upload

After successfully uploading an image, the tool automatically:
1. Marks the image and all linked images as resolved
2. Fetches the next unreviewed image from the API (fresh data)
3. Loads that image for review
4. You continue with the next highest-priority image

## Tips and Best Practices

### Efficient Reviewing

1. **Use autocomplete** - Start typing and select from dropdown
2. **Link before uploading** - Find all related images, link them, then upload once
3. **Let the tool navigate** - After upload, it automatically shows next unreviewed

### Data Quality

1. **Verify extracted data** - OCR isn't perfect, always check
2. **Use MO autocomplete** - Ensures names/locations exist on MO
3. **Be consistent** - Use same location/name format as MO database
4. **Add helpful notes** - Habitat, substrate, abundance, condition
5. **Double-check field codes** - Must be unique

### Working with Others

1. **Don't fight for claims** - If someone has claimed an image, move to next unreviewed
2. **Keep working** - Your heartbeat refreshes your claim automatically
3. **Release quickly** - Don't hold claims on images you're not actively reviewing
4. **Check claim status** - Red warning means someone else is working on it

### Common Workflows

**Simple single image**
1. Load image
2. Fill in data
3. Create new observation
4. Next

**Multiple photos of same specimen**
1. Load first image
2. Fill in data
3. Link related images
4. Create new observation with all images
5. Next

**Adding to existing observation**
1. Load image
2. Fill in data
3. Look up observation ID on MO
4. Add to existing observation
5. Next

**Already uploaded**
1. Load image
2. Fill in field code
3. Mark "Already on MO" with observation/image ID
4. Next

## Troubleshooting

### Cannot Edit Image

**Symptom**: Action buttons and form fields are disabled

**Causes**:
- Someone else has claimed the image
- You navigated using Back/Forward/Jump (view-only)

**Solution**:
- Check claim status banner
- If claimed by someone else, use "Next Unreviewed" to find another image
- If viewing via history, the image loads in view-only mode for safety

### Autocomplete Not Working

**Symptom**: Dropdown doesn't appear when typing

**Causes**:
- Typed less than 2 characters
- No matches in MO database
- Network delay

**Solution**:
- Type at least 2-3 characters
- Wait a moment for results
- Try different search terms
- Check network connection

### Upload Failed

**Symptom**: Error message during image upload

**Common Causes**:
- Missing required fields
- Invalid MO observation ID
- Network timeout
- MO API authentication failure
- Observation doesn't exist

**Solution**:
- Verify all required fields are filled
- Double-check observation ID exists on MO
- Check MO API key configuration (admin)
- Try again after a moment

### Lost Claim While Working

**Symptom**: "Claim conflict" error when submitting

**Causes**:
- Another reviewer claimed the image
- Your claim expired (idle >5 minutes)
- Network interruption

**Solution**:
- Use "Next Unreviewed" to find another image
- Your work is NOT lost - notes are preserved
- Contact other reviewer if needed

### Image Not Advancing After Upload

**Symptom**: Stays on same image after successful upload

**Cause**:
- All images are reviewed (celebration message)
- Navigation state issue

**Solution**:
- Check summary panel - are all images reviewed?
- Click "Next Unreviewed" manually
- Refresh page if needed

### Linked Wrong Image

**Symptom**: Accidentally linked unrelated image

**Solution**:
1. Click the incorrectly linked image in peek strip
2. Click "Unlink" button
3. Linked images must be unlinked BEFORE upload

### Cannot Find Location/Name

**Symptom**: Autocomplete doesn't show the location or name you need

**Solution**:
- Try different search terms (common name vs scientific name)
- Search for higher-level taxa (genus instead of species)
- Location may not exist in MO database yet
- Contact admin to add missing location/name to MO

---

## Getting Help

If you encounter issues not covered in this guide:
1. Check the claim status and error messages
2. Try refreshing the page
3. Contact the system administrator
4. Report bugs via the project issue tracker

**Remember**: The tool automatically saves your progress. Claims expire after 5 minutes, so work efficiently but don't rush.
