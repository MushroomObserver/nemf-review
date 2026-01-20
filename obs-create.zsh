USERNAME="nathan"
PASSWORD="uRF2iYzcYd6kbC6mtkJf"
DROPLET_URL="http://localhost:5001"  # or whatever port you're using

curl -u "$USERNAME:$PASSWORD" -X POST "$DROPLET_URL/api/mo/create_new" \
     -H "Content-Type: application/json" \
     -d '{
      "filename": "IMG_1348.jpeg",
      "field_code": "NEMF-12346-test",
      "date": "2024-09-15",
      "location_id": 2,
      "name_id": 1,
      "notes": "Test observation created via API",
      "project_id": 389
    }'

  # Expected response on success:
  # {
  #   "success": true,
  #   "observation_id": 999888,
  #   "image_id": 777666,
  #   "field_slip": {...}
  # }
