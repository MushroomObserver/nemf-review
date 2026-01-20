USERNAME="nathan"
PASSWORD="uRF2iYzcYd6kbC6mtkJf"
DROPLET_URL="http://localhost:5001"  # or whatever port you're using

curl -u "$USERNAME:$PASSWORD" -X POST "$DROPLET_URL/api/mo/add_to_existing" \
     -H "Content-Type: application/json" \
     -d '{
      "filename": "IMG_1348.jpeg",
      "observation_id": 625778,
      "field_code": "NEMF-12345",
      "project_id": 389
    }'

  # Expected response on success:
  # {
  #   "success": true,
  #   "image_id": 789012,
  #   "observation_id": 123456,
  #   "field_slip": {...}
  # }

