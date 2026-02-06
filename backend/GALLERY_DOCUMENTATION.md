# VejaPRO Gallery Feature Documentation

## Overview

Public gallery feature that displays completed VejaPRO projects with before/after photos. All displayed projects have marketing consent and are certified by experts.

## Architecture

### API Endpoint

**GET** `/api/v1/gallery`

Returns paginated list of gallery items with before/after photos.

#### Query Parameters
- `limit` (int, default: 24, max: 60) - Number of items per page
- `cursor` (string, optional) - Pagination cursor for next page
- `location_tag` (string, optional) - Filter by location (e.g., "vilnius", "kaunas")
- `featured_only` (boolean, optional) - Show only featured projects

#### Response Schema
```json
{
  "items": [
    {
      "id": "evidence_id",
      "project_id": "project_uuid",
      "before_url": "https://...",
      "after_url": "https://...",
      "location_tag": "Vilnius",
      "is_featured": true,
      "uploaded_at": "2026-02-06T18:00:00Z"
    }
  ],
  "next_cursor": "base64_encoded_cursor",
  "has_more": true
}
```

#### Business Rules
- Only shows projects with `marketing_consent = true`
- Only shows projects in `ACTIVE` status
- Requires both SITE_BEFORE and EXPERT_CERTIFICATION evidence
- Evidence must have `show_on_web = true`
- Uses cursor-based pagination (not offset-based)

### UI Route

**GET** `/gallery`

Serves the public gallery HTML page at `@c:\Users\Administrator\Desktop\VejaPRO\backend\app\static\gallery.html:1-993`.

## Features

### 1. Dynamic Grid Layout
- Responsive masonry grid (350px min column width)
- Lazy loading images for performance
- Hover effects with overlay information
- Auto-adjusts to screen size (mobile-friendly)

### 2. Filtering System
- **All Projects** - Shows all gallery items
- **Featured** - Shows only `is_featured = true` items
- **Location filters** - Vilnius, Kaunas, Klaipėda
- Filter buttons in sticky header

### 3. Before/After Slider
- Interactive slider in lightbox modal
- Drag handle to compare before/after photos
- Touch-friendly for mobile devices
- Labels: "Prieš" (Before) and "Po" (After)

### 4. Infinite Scroll
- Automatically loads more items when scrolling
- Uses IntersectionObserver API
- Shows loading spinner during fetch
- Stops when no more items available

### 5. Badges & Tags
- **Featured badge** - ⭐ Išskirtinis (top-right)
- **Location tag** - 📍 Location (bottom-left)
- Both visible on card and in lightbox

### 6. Lightbox Modal
- Full-screen image viewer
- Click outside to close
- Close button (×) in top-right
- Shows project metadata (location, featured status)

## File Structure

```
backend/app/
├── static/
│   ├── gallery.html              # Main gallery UI (new)
│   ├── gallery-dynamic.js        # Legacy JS class (not used by gallery.html)
│   └── landing.html              # Updated with gallery link
├── api/v1/
│   └── projects.py               # Gallery API endpoint (line 1261-1328)
├── schemas/
│   └── project.py                # GalleryItem, GalleryResponse schemas
└── main.py                       # Gallery route (line 234-236)
```

## Usage Examples

### Basic Gallery Load
```javascript
// Fetch first page
GET /api/v1/gallery?limit=24

// Response
{
  "items": [...],
  "next_cursor": "MjAyNi0wMi0wNlQxNjowMDowMC4wMDAwMDA=",
  "has_more": true
}
```

### Load Next Page
```javascript
GET /api/v1/gallery?limit=24&cursor=MjAyNi0wMi0wNlQxNjowMDowMC4wMDAwMDA=
```

### Filter by Location
```javascript
GET /api/v1/gallery?limit=24&location_tag=vilnius
```

### Featured Only
```javascript
GET /api/v1/gallery?limit=24&featured_only=true
```

## Admin Workflow

To add projects to gallery:

1. **Project must reach ACTIVE status**
   - Complete full flow: DRAFT → PAID → CERTIFIED → ACTIVE

2. **Enable marketing consent**
   - Admin UI: Projects → Select project → Toggle marketing consent
   - API: `PUT /api/v1/projects/{id}/marketing-consent`

3. **Upload evidence photos**
   - SITE_BEFORE (before photo)
   - EXPERT_CERTIFICATION (after photo)

4. **Approve evidence for web**
   - Admin endpoint: `POST /api/v1/admin/projects/{id}/evidences/{evidence_id}/approve`
   - Set `show_on_web: true`
   - Optionally set `location_tag` and `is_featured`

5. **Verify in gallery**
   - Visit `/gallery`
   - Project should appear in grid

## Database Schema

### Relevant Tables

**projects**
- `marketing_consent` (boolean) - Must be true
- `status` (enum) - Must be 'ACTIVE'

**evidences**
- `project_id` (uuid, FK)
- `category` (enum) - SITE_BEFORE or EXPERT_CERTIFICATION
- `file_url` (text) - Photo URL
- `show_on_web` (boolean) - Must be true for gallery
- `is_featured` (boolean) - Featured badge
- `location_tag` (text) - Location filter
- `uploaded_at` (timestamp) - Used for cursor pagination

## Performance Considerations

### Pagination
- Uses cursor-based pagination (not offset)
- Cursor encodes `uploaded_at` timestamp
- More efficient for large datasets than OFFSET/LIMIT

### Query Optimization
- Indexed on `(project_id, category, uploaded_at)`
- Filters applied before join
- Limit + 1 pattern to check `has_more`

### Image Loading
- Lazy loading with `loading="lazy"` attribute
- Images only load when near viewport
- Reduces initial page load time

### Caching
- Static assets served with cache headers
- API responses can be cached by CDN (if added)

## Security

### Content Security Policy
- Gallery page uses `_public_headers()`
- Allows images from `https:` (for evidence URLs)
- Allows fonts from Google Fonts
- No inline scripts (all in HTML)

### Data Privacy
- Only shows projects with explicit marketing consent
- No client personal information displayed
- Only shows project ID (truncated to 8 chars)

## Testing

### Manual Testing Checklist
- [ ] Gallery page loads at `/gallery`
- [ ] Grid displays correctly on desktop
- [ ] Grid displays correctly on mobile
- [ ] Filter buttons work (All, Featured, Locations)
- [ ] Infinite scroll loads more items
- [ ] Lightbox opens on card click
- [ ] Before/after slider works (drag handle)
- [ ] Close button closes lightbox
- [ ] Click outside closes lightbox
- [ ] Featured badge shows on featured items
- [ ] Location tags display correctly
- [ ] Empty state shows when no results
- [ ] Error message shows on API failure

### API Testing
```bash
# Test basic endpoint
curl http://localhost:8000/api/v1/gallery

# Test with filters
curl "http://localhost:8000/api/v1/gallery?featured_only=true"
curl "http://localhost:8000/api/v1/gallery?location_tag=vilnius"

# Test pagination
curl "http://localhost:8000/api/v1/gallery?limit=5"
# Use next_cursor from response
curl "http://localhost:8000/api/v1/gallery?cursor=<next_cursor>"
```

## Troubleshooting

### No items in gallery
**Cause:** No projects have marketing consent or are ACTIVE
**Solution:** 
1. Check projects table: `SELECT * FROM projects WHERE marketing_consent = true AND status = 'ACTIVE'`
2. Enable marketing consent via admin UI
3. Ensure project has reached ACTIVE status

### Images not loading
**Cause:** Evidence `show_on_web = false` or missing file_url
**Solution:**
1. Check evidences: `SELECT * FROM evidences WHERE show_on_web = true`
2. Approve evidence via admin endpoint
3. Verify file_url is valid

### Before/after slider not working
**Cause:** Missing SITE_BEFORE evidence
**Solution:**
1. Upload SITE_BEFORE evidence for project
2. Approve with `show_on_web = true`
3. Gallery will show slider if both before and after exist

### Infinite scroll not loading
**Cause:** JavaScript error or API returning `has_more: false`
**Solution:**
1. Check browser console for errors
2. Verify API response has valid `next_cursor`
3. Check if all items already loaded

## Future Enhancements

### Potential Features
- [ ] Search by project ID or description
- [ ] Date range filter (by uploaded_at)
- [ ] Sort options (newest, featured first, location)
- [ ] Share individual project links
- [ ] Download before/after comparison image
- [ ] Admin preview mode (show all projects, not just consented)
- [ ] Gallery statistics (total projects, by location)
- [ ] Integration with Google Maps (show project locations)

### Performance Improvements
- [ ] Add Redis cache for gallery API
- [ ] Implement CDN for images
- [ ] Add image thumbnails (smaller file sizes)
- [ ] Implement progressive image loading
- [ ] Add service worker for offline support

## Related Documentation

- API Specification: `backend/VEJAPRO_TECHNINE_DOKUMENTACIJA_V1.5.md`
- Marketing Module: Feature flag `ENABLE_MARKETING_MODULE`
- Evidence Upload: `POST /api/v1/projects/{id}/evidences`
- Admin Evidence Approval: `POST /api/v1/admin/projects/{id}/evidences/{evidence_id}/approve`

## Changelog

### 2026-02-06
- ✅ Created public gallery UI (`gallery.html`)
- ✅ Added `/gallery` route to FastAPI
- ✅ Integrated with existing `/api/v1/gallery` endpoint
- ✅ Added gallery link to landing page navigation
- ✅ Implemented before/after slider with drag interaction
- ✅ Added filtering (all, featured, location)
- ✅ Implemented infinite scroll with cursor pagination
- ✅ Added lightbox modal for full-screen viewing
- ✅ Created comprehensive documentation

---

**Last Updated:** 2026-02-06  
**Status:** ✅ Production Ready  
**Maintainer:** VejaPRO Development Team
