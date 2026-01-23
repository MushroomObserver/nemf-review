"""
Mushroom Observer API Client

Handles communication with the MO API2 for:
- Uploading images
- Creating observations
- Adding images to existing observations
- Creating/updating field slips
"""

import base64
import mimetypes
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests


class MOAPIError(Exception):
    """Base exception for MO API errors."""
    pass


class MOAPIAuthError(MOAPIError):
    """Authentication failed."""
    pass


class MOAPIConflictError(MOAPIError):
    """Conflict with existing data (e.g., duplicate field slip code)."""
    pass


class MOAPINotFoundError(MOAPIError):
    """Resource not found."""
    pass


class MOAPIClient:
    """Client for Mushroom Observer API2."""

    def __init__(self, api_key: str, base_url: str = 'https://mushroomobserver.org'):
        """
        Initialize MO API client.

        Args:
            api_key: User's MO API key
            base_url: Base URL of MO instance (default: production)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NEMF-Review-Tool/1.0',
            'Accept': 'application/json'
        })

    def _get_auth_header(self) -> Dict[str, str]:
        """Generate HTTP Basic Auth header with API key."""
        # MO API uses the API key as the username, password is empty
        auth_str = f"{self.api_key}:"
        encoded = base64.b64encode(auth_str.encode()).decode()
        return {'Authorization': f'Basic {encoded}'}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an authenticated request to the MO API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., '/api2/observations')
            **kwargs: Additional arguments passed to requests

        Returns:
            Parsed JSON response

        Raises:
            MOAPIAuthError: If authentication fails
            MOAPINotFoundError: If resource not found
            MOAPIConflictError: If request conflicts with existing data
            MOAPIError: For other API errors
        """
        url = f"{self.base_url}{endpoint}"
        skip_auth = kwargs.pop('skip_auth', False)
        headers = kwargs.pop('headers', {})
        if not skip_auth:
            headers.update(self._get_auth_header())

        # Debug logging
        import sys
        sys.stderr.write(f"DEBUG: {method} {url}\n")
        sys.stderr.write(f"DEBUG: Headers: {headers}\n")
        sys.stderr.write(f"DEBUG: API Key (first 10 chars): {self.api_key[:10]}...\n")
        sys.stderr.flush()

        try:
            response = self.session.request(
                method, url, headers=headers, timeout=30, **kwargs
            )

            # Parse response for errors (MO API may return 200 with errors)
            json_response = None
            if response.content:
                try:
                    json_response = response.json()
                except ValueError:
                    # Non-JSON response (e.g., HTML error page)
                    # Leave json_response as None to skip error checking
                    json_response = None

            # Check for errors in response body (MO API format)
            if json_response and 'errors' in json_response:
                errors = json_response['errors']
                if errors:
                    error_msg = errors[0].get('details', 'Unknown error')
                    error_code = errors[0].get('code', '')

                    if 'MustAuthenticate' in error_code or 'Unauthorized' in error_code:
                        raise MOAPIAuthError(f"Authentication failed: {error_msg}")
                    elif 'NotFound' in error_code:
                        raise MOAPINotFoundError(f"Resource not found: {error_msg}")
                    elif 'Conflict' in error_code:
                        raise MOAPIConflictError(f"Conflict: {error_msg}")
                    else:
                        raise MOAPIError(f"API error ({error_code}): {error_msg}")

            # Check HTTP status codes
            if response.status_code == 401:
                raise MOAPIAuthError("API key authentication failed")
            elif response.status_code == 404:
                raise MOAPINotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code == 409:
                raise MOAPIConflictError(f"Conflict: {response.text}")
            elif response.status_code >= 400:
                raise MOAPIError(
                    f"API request failed with status {response.status_code}: "
                    f"{response.text}"
                )

            # Return JSON if present, otherwise empty dict
            if response.content:
                try:
                    return response.json()
                except ValueError as e:
                    # Response is not JSON - likely HTML error page
                    raise MOAPIError(
                        f"API returned non-JSON response (status {response.status_code}): "
                        f"{response.text[:200]}"
                    )
            return {}

        except requests.Timeout:
            raise MOAPIError("Request to MO API timed out")
        except requests.RequestException as e:
            raise MOAPIError(f"Request failed: {str(e)}")

    def get_observation(self, observation_id: int) -> Dict[str, Any]:
        """
        Get observation details.

        Args:
            observation_id: MO observation ID

        Returns:
            Observation data

        Raises:
            MOAPINotFoundError: If observation doesn't exist
        """
        return self._request('GET', f'/api2/observations/{observation_id}')

    def verify_observation_exists(self, observation_id: int) -> bool:
        """
        Check if an observation exists.

        Args:
            observation_id: MO observation ID

        Returns:
            True if exists, False otherwise
        """
        try:
            self.get_observation(observation_id)
            return True
        except MOAPINotFoundError:
            return False

    def verify_image_exists(self, image_id: int) -> bool:
        """
        Check if an image exists.

        Args:
            image_id: MO image ID

        Returns:
            True if exists, False otherwise
        """
        try:
            self._request('GET', f'/api2/images/{image_id}')
            return True
        except MOAPINotFoundError:
            return False

    def upload_image(
        self,
        image_path: str,
        copyright_holder: str,
        license: int = 1,  # Creative Commons Attribution-ShareAlike 3.0
        notes: str = '',
        original_name: str = '',
        **metadata
    ) -> Dict[str, Any]:
        """
        Upload an image to MO.

        Args:
            image_path: Path to image file
            copyright_holder: Name of copyright holder
            license: License ID (default: CC BY-SA 3.0)
            notes: Image notes
            original_name: Original filename
            **metadata: Additional image metadata

        Returns:
            Created image data including image ID

        Raises:
            MOAPIError: If upload fails
        """
        path = Path(image_path)
        if not path.exists():
            raise MOAPIError(f"Image file not found: {image_path}")

        # Prepare multipart form data
        # Note: parameter name is 'upload', not 'upload_file'
        # 'upload_file' is for server-side file paths, 'upload' is for HTTP uploads
        with open(path, 'rb') as image_file:
            files = {
                'upload': (
                    path.name,
                    image_file,
                    mimetypes.guess_type(path)[0] or 'image/jpeg'
                )
            }

            data = {
                'api_key': self.api_key,  # For file uploads, API key goes in form data
                'copyright_holder': copyright_holder,
                'license': license,
                'notes': notes,
                'original_name': original_name or path.name,
                **metadata
            }

            # Don't use auth header for file uploads - API key is in form data
            return self._request('POST', '/api2/images', data=data, files=files, skip_auth=True)

    def create_observation(
        self,
        date: str,  # YYYY-MM-DD format
        location_id: Optional[int] = None,
        location_name: Optional[str] = None,
        name_id: Optional[int] = None,
        notes: str = '',
        image_ids: Optional[List[int]] = None,
        **metadata
    ) -> Dict[str, Any]:
        """
        Create a new observation.

        Args:
            date: Observation date (YYYY-MM-DD)
            location_id: MO location ID
            location_name: Location name (if location_id not provided)
            name_id: MO name ID
            notes: Observation notes
            image_ids: List of image IDs to attach
            **metadata: Additional observation metadata

        Returns:
            Created observation data including observation ID

        Raises:
            MOAPIError: If creation fails
        """
        data = {
            'api_key': self.api_key,
            'date': date,
            'notes': notes,
            **metadata
        }

        if location_id:
            data['location'] = location_id
        elif location_name:
            data['place_name'] = location_name

        if name_id:
            data['name'] = name_id

        if image_ids:
            data['images'] = ','.join(str(id) for id in image_ids)

        return self._request('POST', '/api2/observations', data=data, skip_auth=True)

    def add_image_to_observation(
        self,
        observation_id: int,
        image_id: int
    ) -> Dict[str, Any]:
        """
        Add an existing image to an observation.

        Args:
            observation_id: Target observation ID
            image_id: Image ID to add

        Returns:
            Updated observation data

        Raises:
            MOAPIError: If operation fails
        """
        data = {
            'api_key': self.api_key,
            'id': observation_id,
            'add_images': str(image_id)
        }
        return self._request(
            'PATCH',
            '/api2/observations',
            data=data,
            skip_auth=True  # API key is in form data
        )

    def update_observation_notes(
        self,
        observation_id: int,
        notes: str
    ) -> Dict[str, Any]:
        """
        Update observation notes (appends to existing notes).

        Args:
            observation_id: Target observation ID
            notes: Text to append to notes

        Returns:
            Updated observation data

        Raises:
            MOAPIError: If update fails
        """
        # Get current observation to append notes
        obs = self.get_observation(observation_id)

        # Handle case where API returns just an ID instead of full object
        if not isinstance(obs, dict):
            current_notes = ''
        else:
            current_notes = obs.get('notes', '')

        # Append new notes
        if current_notes:
            updated_notes = f"{current_notes}\n\n{notes}"
        else:
            updated_notes = notes

        data = {
            'api_key': self.api_key,
            'id': observation_id,
            'set_notes': updated_notes
        }
        return self._request(
            'PATCH',
            '/api2/observations',
            data=data,
            skip_auth=True  # API key is in form data
        )

    def get_field_slip_by_code(self, code: str, detail: str = 'low') -> Optional[Dict[str, Any]]:
        """
        Look up field slip by code.

        Args:
            code: Field slip code (e.g., "NEMF-12345")
            detail: Detail level ('low' or 'high') - needed to get observation_id

        Returns:
            Field slip data if found, None if not found

        Raises:
            MOAPIError: If lookup fails (not including 404)
        """
        try:
            response = self._request(
                'GET',
                '/api2/field_slips',
                params={'code': code, 'detail': detail}
            )
            # API returns array of results
            results = response.get('results', [])
            return results[0] if results else None
        except MOAPINotFoundError:
            return None

    def create_field_slip(
        self,
        code: str,
        observation_id: Optional[int] = None,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new field slip.

        Args:
            code: Field slip code (must be unique)
            observation_id: Observation to link to
            project_id: Project to link to

        Returns:
            Created field slip data

        Raises:
            MOAPIConflictError: If code already exists
            MOAPIError: If creation fails
        """
        data = {
            'api_key': self.api_key,
            'code': code
        }

        if observation_id:
            data['observation'] = observation_id
        if project_id:
            data['project'] = project_id

        return self._request('POST', '/api2/field_slips', data=data, skip_auth=True)

    def update_field_slip(
        self,
        field_slip_id: int,
        observation_id: Optional[int] = None,
        code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an existing field slip.

        Args:
            field_slip_id: Field slip ID to update
            observation_id: New observation to link to
            code: New code (must be unique)

        Returns:
            Updated field slip data

        Raises:
            MOAPIConflictError: If new code already exists
            MOAPINotFoundError: If field slip not found
            MOAPIError: If update fails
        """
        data = {
            'api_key': self.api_key,
            'id': field_slip_id
        }

        if observation_id is not None:
            data['set_observation'] = observation_id
        if code is not None:
            data['set_code'] = code

        if len(data) == 2:  # Only api_key and id, no actual updates
            raise MOAPIError("No updates provided")

        return self._request(
            'PATCH',
            '/api2/field_slips',
            data=data,
            skip_auth=True  # API key is in form data
        )

    def create_or_link_field_slip(
        self,
        code: str,
        observation_id: int,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create field slip or link existing one to observation.

        This is a convenience method that handles the common pattern:
        1. Check if field slip exists
        2. If exists and linked to same observation → success
        3. If exists and linked to different observation → error
        4. If doesn't exist → create it

        Args:
            code: Field slip code
            observation_id: Observation to link to
            project_id: Project to link to (optional)

        Returns:
            Field slip data

        Raises:
            MOAPIConflictError: If code exists but linked to different observation
            MOAPIError: If operation fails
        """
        existing = self.get_field_slip_by_code(code)

        if existing:
            # Handle case where API returns just an ID instead of full object
            if isinstance(existing, dict):
                existing_obs_id = existing.get('observation_id')
            else:
                # If API returned just an ID, we can't determine observation linkage
                # Treat as not found to avoid conflict errors
                existing = None
                existing_obs_id = None

        if existing and existing_obs_id:

            if existing_obs_id == observation_id:
                # Already linked correctly
                return existing

            # Conflict: code exists but points to different observation
            raise MOAPIConflictError(
                f"Field slip {code} already exists for observation "
                f"{existing_obs_id}. Cannot link to observation {observation_id}."
            )

        # Create new field slip
        return self.create_field_slip(code, observation_id, project_id)
