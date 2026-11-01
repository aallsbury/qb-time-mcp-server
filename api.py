import requests
from typing import Dict, Any, Optional, List, Union
from utils import setup_logging, log_info, log_error
from datetime import datetime

class BaseAPI:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = 'https://rest.tsheets.com/api/v1'
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

    def format_date_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Format date parameters.
        - modified_since and modified_before are converted to ISO-8601 format
        - start_date and end_date stay in YYYY-MM-DD format
        """
        iso_fields = ['modified_since', 'modified_before']
        formatted_params = params.copy()
        
        # Convert ISO fields to ISO-8601 format
        for field in iso_fields:
            if field in formatted_params and formatted_params[field]:
                # If it's already in ISO format, leave it
                if 'T' in str(formatted_params[field]):
                    continue
                    
                try:
                    # Parse the date and convert to ISO format
                    date = datetime.strptime(str(formatted_params[field]), '%Y-%m-%d')
                    formatted_params[field] = date.strftime('%Y-%m-%dT%H:%M:%SZ')
                except ValueError:
                    # If it's not in expected format, leave it unchanged
                    continue
                    
        return formatted_params

    def add_pagination_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Clean up undefined and null values
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        # Format date parameters
        clean_params = self.format_date_params(clean_params)

        # Convert arrays to comma-separated strings if present, except jobcode_ids
        for key, value in clean_params.items():
            if isinstance(value, list):
                if key == 'jobcode_ids':
                    # Convert jobcode_ids to array of strings but keep as array
                    clean_params[key] = [str(x) for x in value]
                else:
                    clean_params[key] = ','.join(map(str, value))

        # Ensure limit doesn't exceed 200
        if 'limit' in clean_params:
            clean_params['limit'] = min(clean_params['limit'], 200)

        return clean_params

    def handle_axios_error(self, error: Exception, operation: str):
        if isinstance(error, requests.exceptions.RequestException):
            if error.response is not None:
                # The request was made and the server responded with a status code
                # that falls out of the range of 2xx
                error_message = ""
                try:
                    error_message = error.response.json().get('error', {}).get('message') or error.response.reason
                except requests.exceptions.JSONDecodeError:
                    error_message = error.response.reason
                log_error(f"{operation} failed: {error.response.status_code} - {error_message}")
                raise ValueError(f"{operation} failed: {error.response.status_code} - {error_message}")
            elif error.request is not None:
                # The request was made but no response was received
                log_error(f"{operation} failed: No response received")
                raise ValueError(f"{operation} failed: No response received from server")
            else:
                # Something happened in setting up the request
                log_error(f"{operation} failed: {str(error)}")
                raise ValueError(f"{operation} failed: {str(error)}")
        else:
            log_error(f"{operation} failed: {str(error)}")
            raise ValueError(f"{operation} failed: {str(error)}")

    def make_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None):
        """Make a request to the QuickBooks Time API.
        
        Args:
            endpoint: API endpoint to call
            method: HTTP method ('GET' or 'POST')
            params: Query parameters for GET requests
            data: JSON data for POST requests
        """
        try:
            url = f'{self.base_url}/{endpoint}'
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
        except Exception as error:
            return self.handle_axios_error(error, f'{method} request to {endpoint}')

class JobcodeAPI(BaseAPI):
    def get_jobcodes(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a list of jobcodes with powerful filtering capabilities.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                Basic Filters:
                - ids: List of jobcode IDs to filter results
                - name: Filter by name (supports wildcard * from string start)
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                
                Type and Hierarchy Filters:
                - type: Filter by jobcode type ('regular', 'pto', 'paid_break', 'unpaid_break', 'all', default: 'regular')
                - parent_ids: Filter by parent jobcode IDs (0: top-level only, -1: all levels)
                
                Additional Filters:
                - customfields: Include custom fields in response (true/false)
                - modified_before: Filter by modification date (ISO 8601 format)
                - modified_since: Filter by modification date (ISO 8601 format)
                
                Pagination:
                - page: Page number for pagination
                - limit: Number of results per page (max 200)
        
        Returns:
            Dict containing jobcodes information, including for each jobcode:
            - Basic Information:
                - id: Unique identifier
                - name: Jobcode name (max 64 chars)
                - short_code: Shortened alias (alphanumeric only)
                - active: Availability for time entry
            - Hierarchy Information:
                - parent_id: Parent jobcode ID (0 for top-level)
                - has_children: Whether jobcode has child jobcodes
            - Type and Billing:
                - type: 'regular', 'pto', 'paid_break', or 'unpaid_break'
                - billable: Whether jobcode is billable
                - billable_rate: Billing rate when billable is true
            - Assignment:
                - assigned_to_all: Whether jobcode is assigned to all users
            - Custom Fields (if requested):
                - required_customfields: List of required custom field IDs
                - filtered_customfielditems: Custom field value restrictions
            - Metadata:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
                
        Raises:
            ValueError: If parameter validation fails
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            array_params = ['ids', 'parent_ids']
            for param in array_params:
                if param in params and isinstance(params[param], list):
                    clean_params[param] = ','.join(map(str, params[param]))
            
            # Handle name parameter (wildcard supported)
            if 'name' in params:
                clean_params['name'] = str(params['name'])
            
            # Handle enum parameters
            if 'active' in params:
                value = str(params['active']).lower()
                if value not in ['yes', 'no', 'both']:
                    raise ValueError("active must be one of: yes, no, both")
                clean_params['active'] = value
                
            if 'type' in params:
                value = str(params['type']).lower()
                if value not in ['regular', 'pto', 'paid_break', 'unpaid_break', 'all']:
                    raise ValueError("type must be one of: regular, pto, paid_break, unpaid_break, all")
                clean_params['type'] = value
            
            # Handle boolean parameters
            if 'customfields' in params:
                clean_params['customfields'] = str(bool(params['customfields'])).lower()
            
            # Handle date parameters
            date_params = ['modified_before', 'modified_since']
            for param in date_params:
                if param in params:
                    try:
                        # Validate ISO 8601 format
                        datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                        clean_params[param] = params[param]
                    except ValueError:
                        raise ValueError(f"{param} must be in ISO 8601 format")
            
            # Handle pagination parameters
            if 'page' in params:
                if not isinstance(params['page'], (int, float)) or params['page'] < 1:
                    raise ValueError("page must be a positive number")
                clean_params['page'] = int(params['page'])
                
            if 'limit' in params:
                if not isinstance(params['limit'], (int, float)) or params['limit'] < 1 or params['limit'] > 200:
                    raise ValueError("limit must be a number between 1 and 200")
                clean_params['limit'] = int(params['limit'])
        
        try:
            response = self.make_request('jobcodes', params=clean_params)
            
            if not response.get('results', {}).get('jobcodes'):
                raise ValueError('No jobcodes found matching the specified criteria')
                
            return response
            
        except requests.exceptions.RequestException as error:
            # Handle specific error cases
            if error.response is not None:
                if error.response.status_code == 403:
                    raise ValueError('Permission denied. Please verify your access rights.')
                elif error.response.status_code == 429:
                    raise ValueError('Rate limit exceeded. Please try again later.')

            # Handle general request errors
            return self.handle_axios_error(error, 'Fetching jobcodes')

    def get_jobcode(self, id: Union[int, Dict[str, Any]]) -> Dict[str, Any]:
        """Get detailed information about a specific jobcode.
        
        Args:
            id: Either a jobcode ID number or a dictionary containing:
                - id: The unique identifier of the jobcode to retrieve
                - customfields: (Optional) Include custom fields in response (default: False)
        
        Returns:
            Dict containing jobcode information, including:
            - Basic Information:
                - id: Unique identifier
                - name: Jobcode name
                - short_code: Shortened alias
            - Hierarchy Information:
                - parent_id: ID of parent jobcode (0 for top-level)
                - has_children: Whether jobcode has child jobcodes
            - Type and Status:
                - type: 'regular', 'pto', 'paid_break', or 'unpaid_break'
                - active: Whether jobcode is available for time entry
            - Billing Information:
                - billable: Whether jobcode is billable
                - billable_rate: Billing rate when billable is true
            - Assignment:
                - assigned_to_all: Whether jobcode is assigned to all users
            - Custom Fields:
                - required_customfields: List of required custom field IDs
                - filtered_customfielditems: Custom field value restrictions
            - Metadata:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
                
        Raises:
            ValueError: If jobcode ID is invalid or jobcode not found
        """
        # Extract parameters from input
        if isinstance(id, dict):
            jobcode_id = id.get('id')
            include_customfields = id.get('customfields', False)
        else:
            jobcode_id = id
            include_customfields = False
            
        # Validate ID format
        if not isinstance(jobcode_id, int) or jobcode_id <= 0:
            raise ValueError('Invalid jobcode ID. Must be a positive integer.')

        try:
            # Prepare request parameters
            params = {
                'ids': str(jobcode_id),
                'customfields': str(include_customfields).lower()
            }

            # Make API request
            response = self.make_request('jobcodes', params=params)
            
            # Extract jobcode from response
            jobcodes = response.get('results', {}).get('jobcodes', {})
            if not jobcodes:
                raise ValueError('No jobcode data found in response')

            jobcode = jobcodes.get(str(jobcode_id))
            if not jobcode:
                raise ValueError(f'Jobcode {jobcode_id} not found. It may be deleted or you may not have access.')

            return {'result': jobcode}

        except requests.exceptions.RequestException as error:
            # Handle specific error cases
            if error.response is not None:
                if error.response.status_code == 403:
                    raise ValueError(f'Permission denied for jobcode {jobcode_id}. Please verify your access rights.')
                elif error.response.status_code == 429:
                    raise ValueError('Rate limit exceeded. Please try again later.')
                elif error.response.status_code == 417:
                    raise ValueError('Invalid jobcode ID format. Must be a positive integer.')

            # Handle general request errors
            return self.handle_axios_error(error, f'Fetching jobcode {jobcode_id}')

    def get_jobcode_hierarchy(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get the hierarchical structure of jobcodes in your company.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - parent_ids: List of parent IDs to filter by. Special values:
                    * 0: Get only top-level jobcodes
                    * -1: Get all jobcodes regardless of hierarchy
                    * [id1,id2,...]: Get jobcodes with specific parent IDs
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                - type: Filter by jobcode type ('regular', 'pto', 'paid_break', 'unpaid_break', 'all', default: 'regular')
        
        Returns:
            Dict containing jobcodes information, including for each jobcode:
            - Basic Information:
                - id: Unique identifier
                - name: Jobcode name
            - Hierarchy Information:
                - parent_id: ID of parent jobcode (0 for top-level)
                - has_children: Whether jobcode has child jobcodes
            - Status:
                - active: Whether jobcode is available for time entry
            - Metadata:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
                
        Example:
            To get all top-level jobcodes:
            >>> get_jobcode_hierarchy({'parent_ids': [0]})
            
            To get complete hierarchy:
            >>> get_jobcode_hierarchy({'parent_ids': [-1]})
            
            To get children of specific jobcodes:
            >>> get_jobcode_hierarchy({'parent_ids': [123, 456]})
        """
        clean_params = {}
        
        if params:
            # Handle parent_ids parameter
            if 'parent_ids' in params:
                if isinstance(params['parent_ids'], list):
                    # Convert all IDs to strings and join
                    clean_params['parent_ids'] = ','.join(map(str, params['parent_ids']))
                else:
                    raise ValueError("parent_ids must be a list of integers")
            
            # Handle active parameter
            if 'active' in params:
                value = str(params['active']).lower()
                if value not in ['yes', 'no', 'both']:
                    raise ValueError("active must be one of: yes, no, both")
                clean_params['active'] = value
            
            # Handle type parameter
            if 'type' in params:
                value = str(params['type']).lower()
                if value not in ['regular', 'pto', 'paid_break', 'unpaid_break', 'all']:
                    raise ValueError("type must be one of: regular, pto, paid_break, unpaid_break, all")
                clean_params['type'] = value
        
        try:
            response = self.make_request('jobcodes', params=clean_params)
            
            if not response.get('results', {}).get('jobcodes'):
                raise ValueError('No jobcodes found matching the specified criteria')
                
            return response
            
        except requests.exceptions.RequestException as error:
            # Handle specific error cases
            if error.response is not None:
                if error.response.status_code == 403:
                    raise ValueError('Permission denied. Please verify your access rights.')
                elif error.response.status_code == 429:
                    raise ValueError('Rate limit exceeded. Please try again later.')

            # Handle general request errors
            return self.handle_axios_error(error, 'Fetching jobcode hierarchy')

    def get_timesheets(self, params: Optional[Dict[str, Any]] = None):
        """Get timesheets with optional filters."""
        params = self.add_pagination_params(params)
        return self.make_request('timesheets', params=params)

    def get_timesheet(self, id: Union[int, Dict[str, int]]):
        """Get a specific timesheet by ID."""
        if isinstance(id, dict):
            id = id.get('id')
        return self.make_request(f'timesheets/{id}')

    def get_current_timesheets(self, params: Optional[Dict[str, Any]] = None):
        """Get currently active timesheets."""
        # Get today's date in YYYY-MM-DD format for the required start_date filter
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Initialize with required parameters
        clean_params = {
            'on_the_clock': 'yes',
            'start_date': today
        }
        
        if params:
            clean_params.update(params)
            
        return self.make_request('timesheets', params=clean_params)

class TimesheetAPI(BaseAPI):
    """API class for managing timesheets in QuickBooks Time."""
    
    VALID_TIMESHEET_TYPES = {'regular', 'manual'}
    VALID_SUPPLEMENTAL_DATA = {'yes', 'no'}
    VALID_ON_THE_CLOCK = {'yes', 'no', 'both'}
    VALID_JOBCODE_TYPES = {'regular', 'pto', 'paid_break', 'unpaid_break', 'all'}
    
    def get_timesheets(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a list of timesheets with powerful filtering capabilities.
        
        This endpoint retrieves timesheets associated with your company. At least one of
        the required filters must be specified: ids, start_date, modified_before, or
        modified_since.
        
        Args:
            params: Dictionary containing filter parameters:
                Required Filters (at least one):
                - ids: List of timesheet IDs
                - start_date: Return timesheets on/after date (YYYY-MM-DD)
                - modified_before: Return timesheets modified before time (ISO 8601)
                - modified_since: Return timesheets modified since time (ISO 8601)
                
                Optional Filters:
                - end_date: Return timesheets on/before date (YYYY-MM-DD)
                - user_ids: List of user IDs to filter by
                - group_ids: List of group IDs to filter by
                - jobcode_ids: List of jobcode IDs (includes children)
                - payroll_ids: List of payroll IDs
                - on_the_clock: Filter by working status ('yes', 'no', 'both')
                - jobcode_type: Filter by type ('regular', 'pto', 'paid_break', 
                                'unpaid_break', 'all')
                
                Pagination:
                - page: Page number (default: 1)
                - per_page: Results per page (default: 50, max: 50)
        
        Returns:
            Dict containing timesheet information:
            - Common Properties:
                - id: Unique identifier
                - user_id: ID of timesheet owner
                - jobcode_id: ID of associated jobcode
                - locked: Lock status (>0 if locked)
                - notes: Timesheet notes
                - customfields: Custom field values
                - last_modified: Last modification timestamp
                - type: Timesheet type ('regular' or 'manual')
                - on_the_clock: Current working status
                - attached_files: IDs of attached files
                - created_by_user_id: ID of creator
            
            - Regular Timesheet Properties:
                - start: Start time (ISO 8601)
                - end: End time (ISO 8601)
                - date: Timesheet date (YYYY-MM-DD)
            
            - Manual Timesheet Properties:
                - date: Timesheet date (YYYY-MM-DD)
                - duration: Duration in seconds
            
            - Supplemental Data:
                - users: User details
                - jobcodes: Jobcode details
                - customfields: Custom field definitions
        
        Raises:
            ValueError: If no required filter is provided or parameters are invalid
        """
        if not params:
            raise ValueError("At least one required filter must be specified: ids, start_date, modified_before, or modified_since")
        
        clean_params = {}
        required_filters = {'ids', 'start_date', 'modified_before', 'modified_since'}
        
        if not any(filter_name in params for filter_name in required_filters):
            raise ValueError("At least one required filter must be specified: ids, start_date, modified_before, or modified_since")
        
        # Handle array parameters
        array_params = ['ids', 'user_ids', 'group_ids', 'jobcode_ids', 'payroll_ids']
        for param in array_params:
            if param in params:
                if isinstance(params[param], list):
                    clean_params[param] = ','.join(map(str, params[param]))
                else:
                    clean_params[param] = str(params[param])
        
        # Handle date parameters
        date_params = ['start_date', 'end_date']
        for param in date_params:
            if param in params:
                try:
                    # Validate YYYY-MM-DD format
                    datetime.strptime(params[param], '%Y-%m-%d')
                    clean_params[param] = params[param]
                except ValueError:
                    raise ValueError(f"{param} must be in YYYY-MM-DD format")
        
        # Handle ISO 8601 timestamp parameters
        timestamp_params = ['modified_before', 'modified_since']
        for param in timestamp_params:
            if param in params:
                try:
                    # Validate ISO 8601 format
                    datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                    clean_params[param] = params[param]
                except ValueError:
                    raise ValueError(f"{param} must be in ISO 8601 format")
        
        # Handle on_the_clock parameter
        if 'on_the_clock' in params:
            if params['on_the_clock'] not in self.VALID_ON_THE_CLOCK:
                raise ValueError("on_the_clock must be one of: yes, no, both")
            clean_params['on_the_clock'] = params['on_the_clock']
        
        # Handle jobcode_type parameter
        if 'jobcode_type' in params:
            if params['jobcode_type'] not in self.VALID_JOBCODE_TYPES:
                raise ValueError("jobcode_type must be one of: regular, pto, paid_break, unpaid_break, all")
            clean_params['jobcode_type'] = params['jobcode_type']
        
        # Handle pagination
        clean_params.update(self.add_pagination_params(params))
        
        return self.make_request('timesheets', params=clean_params)

    def get_timesheet(self, id: Union[int, Dict[str, int]], supplemental_data: str = 'yes') -> Dict[str, Any]:
        """Get a specific timesheet by ID with detailed information.
        
        This endpoint retrieves comprehensive information about a single timesheet,
        including time entries, custom fields, and optional supplemental data about
        related entities.
        
        Args:
            id: Timesheet ID to retrieve. Can be either:
                - Integer ID value
                - Dictionary with 'id' key containing the ID
            supplemental_data: Include supplemental data ('yes' or 'no', default: 'yes')
        
        Returns:
            Dict containing timesheet information, including:
            - Common Properties:
                - id: Unique identifier
                - user_id: ID of timesheet owner
                - jobcode_id: ID of associated jobcode
                - locked: Lock status (>0 if locked)
                - notes: Timesheet notes
                - customfields: Custom field values
                - last_modified: Last modification timestamp
                - type: Timesheet type ('regular' or 'manual')
                - on_the_clock: Current working status
                - attached_files: IDs of attached files
                - created_by_user_id: ID of creator
            
            - Regular Timesheet Properties:
                - start: Start time (ISO 8601)
                - end: End time (ISO 8601)
                - date: Timesheet date (YYYY-MM-DD)
            
            - Manual Timesheet Properties:
                - date: Timesheet date (YYYY-MM-DD)
                - duration: Duration in seconds
            
            - Supplemental Data (if requested):
                - users: User details
                - jobcodes: Jobcode details
                - customfields: Custom field definitions
        
        Raises:
            ValueError: If parameters are invalid
            TypeError: If id parameter is of wrong type
        """
        # Handle different id parameter types
        if isinstance(id, dict):
            timesheet_id = id.get('id')
            if timesheet_id is None:
                raise ValueError("Dictionary parameter must contain 'id' key")
        elif isinstance(id, (int, str)):
            timesheet_id = str(id)
        else:
            raise TypeError("id must be an integer, string, or dictionary with 'id' key")
        
        # Validate supplemental_data parameter
        if supplemental_data not in self.VALID_SUPPLEMENTAL_DATA:
            raise ValueError("supplemental_data must be one of: yes, no")
        
        # Build parameters
        params = {
            'ids': timesheet_id,
            'supplemental_data': supplemental_data
        }
        
        return self.make_request('timesheets', params=params)
    
    def get_current_timesheets(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get currently active timesheets (users who are 'on the clock').
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - user_ids: List of user IDs to filter active timesheets
                - group_ids: List of group IDs to filter users
                - jobcode_ids: List of jobcode IDs to filter timesheets
                - supplemental_data: Include supplemental data ('yes' or 'no', default 'yes')
                - start_date: Optional start date to override the default (today)
        
        Returns:
            API response containing current timesheets and optional supplemental data
        """
        # Get today's date in YYYY-MM-DD format for the required start_date filter
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Initialize with required parameters
        clean_params = {
            'on_the_clock': 'yes',
            'start_date': today
        }
        
        if params:
            # Override start_date if provided
            if 'start_date' in params:
                clean_params['start_date'] = params['start_date']
                
            # Handle array parameters
            array_params = ['user_ids', 'group_ids', 'jobcode_ids']
            for param_name in array_params: # Corrected variable name here
                if param_name in params:
                    if isinstance(params[param_name], list):
                        clean_params[param_name] = ','.join(map(str, params[param_name]))
                    else:
                        clean_params[param_name] = str(params[param_name])
            
            # Handle supplemental_data parameter
            if 'supplemental_data' in params:
                if params['supplemental_data'] not in self.VALID_SUPPLEMENTAL_DATA:
                    raise ValueError("supplemental_data must be one of: yes, no")
                clean_params['supplemental_data'] = params['supplemental_data']
        
        return self.make_request('timesheets', params=clean_params)

class UserAPI(BaseAPI):
    def get_users(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get users with advanced filtering options.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - ids: List of user IDs to filter on
                - not_ids: List of user IDs to exclude
                - employee_numbers: List of employee numbers to filter on
                - usernames: List of usernames to filter on
                - group_ids: Filter users by their group membership
                - not_group_ids: Exclude users from specific groups
                - payroll_ids: Filter by payroll identification numbers
                - active: Filter by user status ('yes', 'no', 'both')
                - first_name: Filter by first name
                - last_name: Filter by last name
                - modified_before: Only users modified before this date/time
                - modified_since: Only users modified since this date/time
                - page: Page number for pagination
                - per_page: Number of results per page (max 200)
        
        Returns:
            API response containing matched users
        """
        # Clean and format parameters
        clean_params = self.add_pagination_params(params or {})
        
        # Convert array parameters to comma-separated strings
        array_params = [
            'ids', 'not_ids', 'employee_numbers', 'usernames',
            'group_ids', 'not_group_ids', 'payroll_ids'
        ]
        
        for param in array_params:
            if param in clean_params and isinstance(clean_params[param], list):
                clean_params[param] = ','.join(map(str, clean_params[param]))
        
        # Handle pagination parameter name difference (per_page -> limit)
        if 'per_page' in clean_params:
            clean_params['limit'] = clean_params.pop('per_page')
            
        return self.make_request('users', params=clean_params)

    def get_user(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get user details with advanced filtering options.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - ids: List of user IDs to filter on
                - active: 'yes' or 'no' to filter on active status
                - first_name: Filter by first name
                - last_name: Filter by last name
                - modified_before: Only users modified before this date/time
                - modified_since: Only users modified since this date/time
                - page: Page number to return
                - per_page: Number of results per page
                - payroll_ids: List of payroll IDs to filter on
        
        Returns:
            API response containing matched users
        """
        # Clean and format parameters
        clean_params = self.add_pagination_params(params)
        
        # Convert arrays to comma-separated strings
        if 'ids' in clean_params and isinstance(clean_params['ids'], list):
            clean_params['ids'] = ','.join(map(str, clean_params['ids']))
        if 'payroll_ids' in clean_params and isinstance(clean_params['payroll_ids'], list):
            clean_params['payroll_ids'] = ','.join(map(str, clean_params['payroll_ids']))
            
        return self.make_request('users', params=clean_params)

    def get_current_user(self) -> Dict[str, Any]:
        """Get detailed information about the currently authenticated user.

        Returns a comprehensive user object containing:
        - Basic Information: ID, name, email, contact details, etc.
        - Employment Details: hire date, employee number, payroll ID, etc.
        - Status Information: active status, last modified, last active, etc.
        - Company Details: company name, client URL, etc.
        - Profile Settings: preferred name, pronouns, profile image
        - PTO Information: PTO balances by jobcode
        - Timesheet Status: submission and approval dates
        - Permissions: detailed access rights and capabilities
        - Custom Fields: any custom field values associated with the user

        Returns:
            Dict containing user information and supplemental data (groups, jobcodes)
        """
        return self.make_request('current_user')

    def get_groups(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get information about groups in your company.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - ids: List of group IDs to filter results
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                - manager_ids: List of manager user IDs to filter groups
                - supplemental_data: Include supplemental data ('yes', 'no', default: 'yes')
        
        Returns:
            Dict containing groups information, including:
            - Basic Information: ID, name, active status
            - Manager Information: List of manager user IDs
            - Time Entry Settings: Various settings for time entry behavior
            - Timesheet Settings: Approval and submission requirements
            - Metadata: created date, last modified date
            - Supplemental Data: Manager details (if requested)
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            array_params = ['ids', 'manager_ids']
            for param in array_params:
                if param in params and isinstance(params[param], list):
                    clean_params[param] = ','.join(map(str, params[param]))
            
            # Handle enum parameters
            if 'active' in params:
                value = str(params['active']).lower()
                if value not in ['yes', 'no', 'both']:
                    raise ValueError("active must be one of: yes, no, both")
                clean_params['active'] = value
            
            # Handle supplemental_data parameter
            if 'supplemental_data' in params:
                value = str(params['supplemental_data']).lower()
                if value not in ['yes', 'no']:
                    raise ValueError("supplemental_data must be either 'yes' or 'no'")
                clean_params['supplemental_data'] = value
        
        return self.make_request('groups', params=clean_params)

    def get_custom_fields(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get custom fields configured in your company.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - ids: List of custom field IDs to filter results
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                - applies_to: Filter by object type ('timesheet', 'user', 'jobcode')
                - value_type: Filter by field value type ('managed-list', 'free-form')
        
        Returns:
            Dict containing custom fields information, including:
            - Basic Information: ID, name, short code
            - Field Configuration: type, applies_to, required status
            - Value Settings: value_type, value_options (for managed lists)
            - UI Preferences: ui_preference, regex_filter
            - Access Controls: show/edit permissions for different user types
            - Metadata: created date, last modified date
        """
        clean_params = {}
        
        if params:
            # Handle array of IDs
            if 'ids' in params and isinstance(params['ids'], list):
                clean_params['ids'] = ','.join(map(str, params['ids']))
            
            # Handle enum parameters
            enum_params = {
                'active': ['yes', 'no', 'both'],
                'applies_to': ['timesheet', 'user', 'jobcode'],
                'value_type': ['managed-list', 'free-form']
            }
            
            for param, valid_values in enum_params.items():
                if param in params:
                    value = str(params[param]).lower()
                    if value not in valid_values:
                        raise ValueError(f"{param} must be one of: {', '.join(valid_values)}")
                    clean_params[param] = value
        
        return self.make_request('customfields', params=clean_params)

class ProjectManagementAPI(BaseAPI):
    """API class for managing projects and related activities in QuickBooks Time."""
    
    VALID_ACTIVITY_TYPES = {
        'status_change', 'note_added', 'budget_change', 
        'date_change', 'custom_field_change'
    }
    
    VALID_PROJECT_STATUS = {'active', 'completed', 'on-hold'}
    VALID_BUDGET_TYPES = {'hours', 'money'}
    VALID_ACTIVE_STATUS = {'yes', 'no', 'both'}
    
    def get_projects(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get information about projects configured in your company.
        
        Projects help organize work and track time against specific initiatives or clients.
        This endpoint provides comprehensive project data including budgets, schedules,
        and custom field values.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                Basic Filters:
                - ids: List of project IDs to filter results
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                
                Association Filters:
                - client_id: Filter by client ID
                - jobcode_id: Filter by associated jobcode ID
                
                Date Filters:
                - modified_before: Filter by modification date (ISO 8601 format)
                - modified_since: Filter by modification date (ISO 8601 format)
                
                Pagination:
                - page: Page number to return (default: 1)
                - per_page: Number of results per page (default: 50, max: 50)
        
        Returns:
            Dict containing project information, including for each project:
            - Basic Information:
                - id: Unique identifier
                - name: Project name
                - active: Project status
                - project_code: Unique project identifier
            
            - Client and Jobcode Association:
                - client_id: Associated client ID
                - jobcode_id: Associated jobcode ID
            
            - Budget Information:
                - billable: Billable status
                - budget: Project budget
                - budget_type: Budget type ('hours' or 'money')
                - budget_used: Amount of budget used
            
            - Scheduling:
                - start_date: Project start date (YYYY-MM-DD)
                - end_date: Project end date (YYYY-MM-DD)
                - estimated_completion_date: Expected completion date
                - estimated_hours: Estimated project hours
            
            - Project Details:
                - description: Project description
                - notes: Additional notes
                - status: Project status ('active', 'completed', 'on-hold')
            
            - Custom Fields:
                - customfields: Dictionary of custom field values
            
            - Timestamps:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
            
            - Supplemental Data:
                - clients: Client details
                - jobcodes: Jobcode details
        
        Raises:
            ValueError: If parameter validation fails
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            if 'ids' in params:
                if isinstance(params['ids'], list):
                    clean_params['ids'] = ','.join(map(str, params['ids']))
                else:
                    clean_params['ids'] = str(params['ids'])
            
            # Handle active status
            if 'active' in params:
                status = str(params['active']).lower()
                if status not in self.VALID_ACTIVE_STATUS:
                    raise ValueError("active must be one of: yes, no, both")
                clean_params['active'] = status
            
            # Handle single ID parameters
            id_params = ['client_id', 'jobcode_id']
            for param in id_params:
                if param in params:
                    clean_params[param] = str(params[param])
            
            # Handle date parameters
            date_params = ['modified_before', 'modified_since']
            for param in date_params:
                if param in params:
                    try:
                        # Validate ISO 8601 format
                        datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                        clean_params[param] = params[param]
                    except (ValueError, AttributeError):
                        raise ValueError(f"{param} must be in ISO 8601 format")
            
            # Handle pagination parameters
            if 'page' in params:
                if not isinstance(params['page'], (int, float)) or params['page'] < 1:
                    raise ValueError("page must be a positive number")
                clean_params['page'] = int(params['page'])
            
            if 'per_page' in params:
                if not isinstance(params['per_page'], (int, float)) or not (1 <= params['per_page'] <= 50):
                    raise ValueError("per_page must be between 1 and 50")
                clean_params['per_page'] = int(params['per_page'])
        
        return self.make_request('projects', params=clean_params)

    def get_project_activities(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get activity logs for projects, including status changes, updates, and user interactions.
        
        This endpoint helps track project history and monitor changes over time. It's useful for:
        - Monitoring project progress and status changes
        - Tracking budget modifications
        - Following project timeline adjustments
        - Reviewing user interactions and notes
        
        Args:
            params: Dictionary containing any of the following optional filters:
                Project and User Filters:
                - project_ids: List of project IDs to filter activities
                - user_ids: List of user IDs to filter activities
                
                Activity Type Filter:
                - activity_types: List of activity types to filter
                  ('status_change', 'note_added', 'budget_change',
                   'date_change', 'custom_field_change')
                
                Date Filters:
                - modified_before: Filter by modification date (ISO 8601 format)
                - modified_since: Filter by modification date (ISO 8601 format)
                
                Pagination:
                - page: Page number to return (default: 1)
                - per_page: Number of results per page (default: 50, max: 50)
        
        Returns:
            Dict containing project activities information, including:
            - Basic Information:
                - id: Unique identifier
                - project_id: Associated project ID
                - user_id: User who performed the activity
            
            - Activity Details:
                - activity_type: Type of activity
                - activity_data: Object containing:
                    - field: Changed field name (for changes)
                    - old_value: Previous value (for changes)
                    - new_value: Updated value (for changes)
                    - note: Additional information (for notes)
            
            - Timestamps:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
            
            - Supplemental Data:
                - users: User details
                - projects: Project details
        
        Raises:
            ValueError: If parameter validation fails
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            array_params = ['project_ids', 'user_ids']
            for param in array_params:
                if param in params:
                    if isinstance(params[param], list):
                        clean_params[param] = ','.join(map(str, params[param]))
                    else:
                        clean_params[param] = str(params[param])
            
            # Handle activity types
            if 'activity_types' in params:
                types = params['activity_types']
                if isinstance(types, str):
                    types = [types]
                invalid_types = set(types) - self.VALID_ACTIVITY_TYPES
                if invalid_types:
                    raise ValueError(f"Invalid activity type(s): {invalid_types}")
                clean_params['activity_types'] = ','.join(types)
            
            # Handle date parameters
            date_params = ['modified_before', 'modified_since']
            for param in date_params:
                if param in params:
                    try:
                        # Validate ISO 8601 format
                        datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                        clean_params[param] = params[param]
                    except (ValueError, AttributeError):
                        raise ValueError(f"{param} must be in ISO 8601 format")
            
            # Handle pagination parameters
            if 'page' in params:
                if not isinstance(params['page'], (int, float)) or params['page'] < 1:
                    raise ValueError("page must be a positive number")
                clean_params['page'] = int(params['page'])
            
            if 'per_page' in params:
                if not isinstance(params['per_page'], (int, float)) or not (1 <= params['per_page'] <= 50):
                    raise ValueError("per_page must be between 1 and 50")
                clean_params['per_page'] = int(params['per_page'])
        
        return self.make_request('project_activities', params=clean_params)

class LastModifiedAPI(BaseAPI):
    """API class for retrieving last modified timestamps for various entities."""
    
    # Valid entity types that can be queried
    VALID_TYPES = {
        'users', 'groups', 'jobcodes', 'timesheets', 'custom_fields',
        'projects', 'locations', 'clients'
    }
    
    def get_last_modified(self, types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get the most recent modification timestamps for various entities.
        
        This endpoint is useful for:
        - Data synchronization
        - Implementing incremental updates
        - Optimizing API calls
        - Maintaining data consistency
        
        Args:
            types: Optional list of entity types to filter results. Available types:
                - users: User accounts and settings
                - groups: User groups and permissions
                - jobcodes: Job codes and tasks
                - timesheets: Time entries
                - custom_fields: Custom field definitions
                - projects: Project details
                - locations: Geofencing locations
                - clients: Client information
                If None, returns timestamps for all entity types.
        
        Returns:
            Dict containing last modified timestamps for requested entities:
            {
                "results": {
                    "last_modified_timestamps": {
                        "users": "<timestamp>",
                        "groups": "<timestamp>",
                        ...
                    }
                }
            }
            
        Raises:
            ValueError: If any requested type is invalid
        """
        params = {}
        
        if types:
            # Validate all types before making the request
            invalid_types = set(types) - self.VALID_TYPES
            if invalid_types:
                raise ValueError(
                    f"Invalid entity type(s): {', '.join(invalid_types)}. "
                    f"Valid types are: {', '.join(sorted(self.VALID_TYPES))}"
                )
            
            # Convert list to comma-separated string
            params['types'] = ','.join(types)
        
        try:
            response = self.make_request('last_modified_timestamps', params=params)
            
            if not response.get('results', {}).get('last_modified_timestamps'):
                raise ValueError('No timestamp data returned from the API')
                
            return response
            
        except requests.exceptions.RequestException as error:
            # Handle specific error cases
            if error.response is not None:
                if error.response.status_code == 403:
                    raise ValueError('Permission denied. Please verify your access rights.')
                elif error.response.status_code == 429:
                    raise ValueError('Rate limit exceeded. Please try again later.')
            
            # Handle general request errors
            return self.handle_axios_error(error, 'Fetching last modified timestamps')

class NotificationsAPI(BaseAPI):
    """API class for managing notifications in QuickBooks Time.
    
    This class provides methods to retrieve notifications for users, including system alerts,
    reminders, and important updates about timesheets, approvals, and other events.
    """
    
    VALID_NOTIFICATION_TYPES = {
        'timesheet_pending', 'timesheet_approved', 'timesheet_denied', 
        'reminder', 'alert'
    }
    
    VALID_READ_STATUS = {'read', 'unread', 'both'}
    
    def get_notifications(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get notifications with powerful filtering capabilities.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                User and Type Filters:
                - user_ids: List of user IDs to filter notifications
                - notification_types: List of notification types to filter
                  ('timesheet_pending', 'timesheet_approved', 'timesheet_denied',
                   'reminder', 'alert')
                
                Status Filters:
                - read_status: Filter by read status ('read', 'unread', 'both')
                
                Date Filters:
                - modified_before: Filter by modification date (ISO 8601 format)
                - modified_since: Filter by modification date (ISO 8601 format)
                
                Pagination:
                - page: Page number to return (default: 1)
                - per_page: Number of results per page (default: 50, max: 50)
        
        Returns:
            Dict containing notifications information, including for each notification:
            - Basic Information:
                - id: Unique identifier
                - user_id: ID of the user the notification is for
                - type: Type of notification
                - title: Notification title
                - message: Notification message
            - Status Information:
                - read: Whether notification has been read
                - priority: Notification priority level
            - Related Objects:
                - linked_object_type: Type of linked object
                - linked_object_id: ID of linked object
            - Timing Information:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
                - expires: Expiration timestamp
            - Additional Data:
                - metadata: Notification-specific metadata
            
        Raises:
            ValueError: If parameter validation fails
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            if 'user_ids' in params:
                if isinstance(params['user_ids'], list):
                    clean_params['user_ids'] = ','.join(map(str, params['user_ids']))
                else:
                    clean_params['user_ids'] = str(params['user_ids'])
            
            # Handle notification types
            if 'notification_types' in params:
                types = params['notification_types']
                if isinstance(types, str):
                    types = [types]
                invalid_types = set(types) - self.VALID_NOTIFICATION_TYPES
                if invalid_types:
                    raise ValueError(f"Invalid notification type(s): {invalid_types}")
                clean_params['notification_types'] = ','.join(types)
            
            # Handle read status
            if 'read_status' in params:
                status = str(params['read_status']).lower()
                if status not in self.VALID_READ_STATUS:
                    raise ValueError("read_status must be one of: read, unread, both")
                clean_params['read_status'] = status
            
            # Handle date parameters
            date_params = ['modified_before', 'modified_since']
            for param in date_params:
                if param in params:
                    try:
                        # Validate ISO 8601 format
                        datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                        clean_params[param] = params[param]
                    except (ValueError, AttributeError):
                        raise ValueError(f"{param} must be in ISO 8601 format")
            
            # Handle pagination parameters
            if 'page' in params:
                if not isinstance(params['page'], (int, float)) or params['page'] < 1:
                    raise ValueError("page must be a positive number")
                clean_params['page'] = int(params['page'])
            
            if 'per_page' in params:
                if not isinstance(params['per_page'], (int, float)) or not (1 <= params['per_page'] <= 50):
                    raise ValueError("per_page must be between 1 and 50")
                clean_params['per_page'] = int(params['per_page'])
        
        return self.make_request('notifications', params=clean_params)

class AdditionalFeaturesAPI(BaseAPI):
    """API class for accessing additional QuickBooks Time features."""
    
    def get_managed_clients(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get information about managed clients in your company.
        
        This endpoint is useful for:
        - Data synchronization
        - Implementing incremental updates
        - Optimizing API calls
        - Maintaining data consistency
        
        Args:
            params: Dictionary containing any of the following optional filters:
                Basic Filters:
                - ids: List of client IDs to filter results
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                
                Date Filters:
                - modified_before: Filter by modification date (ISO 8601 format)
                - modified_since: Filter by modification date (ISO 8601 format)
                
                Pagination:
                - page: Page number to return (default: 1)
                - per_page: Number of results per page (default: 50, max: 50)
        
        Returns:
            Dict containing managed clients information, including for each client:
            - Basic Information:
                - id: Unique identifier
                - name: Client name
                - company: Company name
                - active: Whether client is active
            - Contact Information:
                - address: Street address
                - city: City
                - state: State/province
                - zip: Postal code
                - country: Country
                - phone: Phone number
                - email: Email address
                - fax: Fax number
                - website: Website URL
            - Business Information:
                - tax_number: Tax identification number
                - notes: Additional notes
            - Billing Settings:
                - rate: Default billing rate
                - currency: Billing currency
                - billing_increment: Time increment for billing
                - overtime_multiplier: Rate multiplier for overtime
                - overtime_threshold: Hours threshold for overtime
                - billable_types: List of billable job types
            - System Settings:
                - timezone: Client's timezone
            - Custom Fields:
                - customfields: Dictionary of custom field values
            - Metadata:
                - created: Creation timestamp
                - last_modified: Last modification timestamp
                
        Raises:
            ValueError: If parameter validation fails
        """
        clean_params = {}
        
        if params:
            # Handle array parameters
            if 'ids' in params:
                if isinstance(params['ids'], list):
                    clean_params['ids'] = ','.join(map(str, params['ids']))
                else:
                    raise ValueError("ids must be a list of integers")
            
            # Handle enum parameters
            if 'active' in params:
                value = str(params['active']).lower()
                if value not in ['yes', 'no', 'both']:
                    raise ValueError("active must be one of: yes, no, both")
                clean_params['active'] = value
            
            # Handle date parameters
            date_params = ['modified_before', 'modified_since']
            for param in date_params:
                if param in params:
                    try:
                        # Validate ISO 8601 format
                        datetime.fromisoformat(params[param].replace('Z', '+00:00'))
                        clean_params[param] = params[param]
                    except (ValueError, AttributeError):
                        raise ValueError(f"{param} must be in ISO 8601 format (YYYY-MM-DDThh:mm:ss±hh:mm)")
            
            # Handle pagination parameters
            if 'page' in params:
                if not isinstance(params['page'], (int, float)) or params['page'] < 1:
                    raise ValueError("page must be a positive number")
                clean_params['page'] = int(params['page'])
                
            if 'per_page' in params:
                if not isinstance(params['per_page'], (int, float)) or params['per_page'] < 1 or params['per_page'] > 50:
                    raise ValueError("per_page must be a number between 1 and 50")
                clean_params['per_page'] = int(params['per_page'])
        
        try:
            response = self.make_request('managed_clients', params=clean_params)
            
            if not response.get('results', {}).get('managed_clients'):
                raise ValueError('No managed clients found matching the specified criteria')
                
            return response
            
        except requests.exceptions.RequestException as error:
            # Handle specific error cases
            if error.response is not None:
                if error.response.status_code == 403:
                    raise ValueError('Permission denied. Please verify your access rights.')
                elif error.response.status_code == 429:
                    raise ValueError('Rate limit exceeded. Please try again later.')
            
            # Handle general request errors
            return self.handle_axios_error(error, 'Fetching managed clients')

class ReportsAPI(BaseAPI):
    """API class for generating various reports from QuickBooks Time data."""
    
    VALID_JOBCODE_TYPES = {'regular', 'pto', 'paid_break', 'unpaid_break'}

    def get_current_totals(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get real-time totals for currently active time entries.

        This report provides a snapshot of current totals (shift and day) 
        for users, particularly those currently on the clock. The request
        is made via POST with parameters in a 'data' object in the JSON body.

        Args:
            params: Dictionary containing any of the following optional filters:
                - user_ids (Union[List[int], str, int]): A list of user IDs, a 
                  comma-separated string of user IDs, or a single user ID.
                  Only totals for these users will be included.
                - group_ids (Union[List[int], str, int]): A list of group IDs, a
                  comma-separated string of group IDs, or a single group ID.
                  Only totals for users from these groups will be included.
                - on_the_clock (str): 'yes', 'no', or 'both'. 
                  If a user is `on_the_clock`, it means the user is currently 
                  working. The API defaults to 'no' if not provided by the client,
                  but this implementation doesn't set a default if not in params.
                - page (int): Represents the page of results to retrieve. Default is 1.
                - limit (int): Represents how many results to retrieve per request. 
                  Default is 200. Max is 200. Must be > 0 and <= 200.
                - order_by (str): Attribute name by which to order the result data, 
                  one of: 'username', 'first_name', 'last_name', 'group_name', 
                  'group_id', 'shift_seconds', or 'day_seconds'.
                - order_desc (bool): If True, result data will be ordered descending 
                  by the attribute specified in `order_by`.

        Returns:
            Dict: API response containing current totals report.
        
        Raises:
            ValueError: If `on_the_clock` or `limit` parameters are invalid.
        """
        data_payload = {}
        
        if params:
            # Handle user_ids: convert list to comma-separated string
            if 'user_ids' in params and params['user_ids'] is not None:
                if isinstance(params['user_ids'], list):
                    data_payload['user_ids'] = ','.join(map(str, params['user_ids']))
                else: # Assume it's already a string or a single int that can be stringified
                    data_payload['user_ids'] = str(params['user_ids'])
            
            # Handle group_ids: convert list to comma-separated string
            if 'group_ids' in params and params['group_ids'] is not None:
                if isinstance(params['group_ids'], list):
                    data_payload['group_ids'] = ','.join(map(str, params['group_ids']))
                else: # Assume it's already a string or a single int that can be stringified
                    data_payload['group_ids'] = str(params['group_ids'])

            # Handle other documented parameters directly
            allowed_params = ['on_the_clock', 'page', 'limit', 'order_by', 'order_desc']
            for param_name in allowed_params:
                if param_name in params and params[param_name] is not None:
                    data_payload[param_name] = params[param_name]
            
            # Validate 'on_the_clock' if it's in the payload (i.e., was provided in params)
            if 'on_the_clock' in data_payload and data_payload['on_the_clock'] not in ['yes', 'no', 'both']:
                raise ValueError("on_the_clock must be one of: 'yes', 'no', or 'both'")

            # Validate 'limit' if it's in the payload
            if 'limit' in data_payload:
                limit_val = data_payload['limit']
                if not (isinstance(limit_val, int) and 0 < limit_val <= 200):
                    raise ValueError("limit must be an integer greater than zero and not greater than 200.")
        
        # The API expects the filters object under a 'data' key in the POST body
        # If data_payload is empty, we still send {'data': {}} as per typical API behavior for POST with optional filters
        post_body = {'data': data_payload}
        
        # Call the make_request method specific to ReportsAPI which handles POST
        return self.make_request(endpoint='reports/current_totals', method='POST', data=post_body)

    def get_payroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get payroll data with detailed time entries grouped by user and pay period.
        
        This endpoint is designed for:
        - Payroll processing and calculations
        - Time tracking analysis and reporting
        - PTO and overtime monitoring
        
        Args:
            params: Dictionary containing the following parameters:
                Required:
                - start_date: Start of pay period (YYYY-MM-DD format)
                - end_date: End of pay period (YYYY-MM-DD format)
                
                Optional:
                - user_ids: List of user IDs to filter payroll
                - group_ids: List of group IDs to filter users
                - include_zero_time: Include users with no time entries (default: false)
        
        Returns:
            Dict containing payroll report data, including:
            - Overall Totals:
                - total_re_seconds: Regular time in seconds
                - total_ot_seconds: Overtime in seconds
                - total_dt_seconds: Double time in seconds
                - total_pto_seconds: PTO time in seconds
                - total_work_seconds: Total work time in seconds
            
            - Per User Data:
                - All the same totals as above
                - timesheet_count: Number of timesheets
                - daily_totals: Breakdown by date, including:
                    - re_seconds: Regular time
                    - ot_seconds: Overtime
                    - dt_seconds: Double time
                    - pto_seconds: PTO time
                    - work_seconds: Total work time
                    - timesheet_count: Number of timesheets
            
            - Supplemental Data:
                - users: User details
        
        Raises:
            ValueError: If required parameters are missing or parameter validation fails
        """
        if not params.get('start_date'):
            raise ValueError("start_date is required (format: YYYY-MM-DD)")
        if not params.get('end_date'):
            raise ValueError("end_date is required (format: YYYY-MM-DD)")
            
        clean_params = {}
        
        # Handle date parameters
        try:
            # Validate date format
            datetime.strptime(params['start_date'], '%Y-%m-%d')
            datetime.strptime(params['end_date'], '%Y-%m-%d')
            clean_params['start_date'] = params['start_date']
            clean_params['end_date'] = params['end_date']
        except ValueError:
            raise ValueError("Dates must be in YYYY-MM-DD format")
            
        # Handle array parameters
        array_params = ['user_ids', 'group_ids']
        for param in array_params:
            if param in params:
                if isinstance(params[param], list):
                    clean_params[param] = ','.join(map(str, params[param]))
                else:
                    clean_params[param] = str(params[param])
        
        # Handle boolean parameters
        if 'include_zero_time' in params:
            clean_params['include_zero_time'] = str(bool(params['include_zero_time'])).lower()
        
        return self.make_request('payroll', params=clean_params) # Should be self.make_request from BaseAPI for GET

    def get_payroll_by_jobcode(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get payroll data grouped by jobcode with detailed time entries.
        
        This endpoint is particularly useful for:
        - Project costing and budget monitoring
        - Client billing and invoice generation
        - Departmental time tracking and analysis
        
        Args:
            params: Dictionary containing the following parameters:
                Required:
                - start_date: Start of pay period (YYYY-MM-DD format)
                - end_date: End of pay period (YYYY-MM-DD format)
                
                Optional:
                - user_ids: List of user IDs to filter payroll
                - group_ids: List of group IDs to filter users
                - jobcode_ids: List of jobcode IDs to filter
                - jobcode_type: Filter by type ('regular', 'pto', 'paid_break', 'unpaid_break')
                - include_zero_time: Include jobcodes with no time entries (default: false)
        
        Returns:
            Dict containing payroll report data, including:
            - Overall Totals:
                - total_re_seconds: Regular time in seconds
                - total_ot_seconds: Overtime in seconds
                - total_dt_seconds: Double time in seconds
                - total_work_seconds: Total work time in seconds
            
            - Per Jobcode Data:
                - All the same totals as above
                - timesheet_count: Number of timesheets
                - user_totals: Breakdown by user
                - daily_totals: Breakdown by date
            
            - Supplemental Data:
                - users: User details
                - jobcodes: Jobcode details
        
        Raises:
            ValueError: If required parameters are missing or parameter validation fails
        """
        if not params.get('start_date'):
            raise ValueError("start_date is required (format: YYYY-MM-DD)")
        if not params.get('end_date'):
            raise ValueError("end_date is required (format: YYYY-MM-DD)")
            
        clean_params = {}
        
        # Handle date parameters
        try:
            # Validate date format
            datetime.strptime(params['start_date'], '%Y-%m-%d')
            datetime.strptime(params['end_date'], '%Y-%m-%d')
            clean_params['start_date'] = params['start_date']
            clean_params['end_date'] = params['end_date']
        except ValueError:
            raise ValueError("Dates must be in YYYY-MM-DD format")
            
        # Handle array parameters
        array_params = ['user_ids', 'group_ids', 'jobcode_ids']
        for param in array_params:
            if param in params:
                if isinstance(params[param], list):
                    clean_params[param] = ','.join(map(str, params[param]))
                else:
                    clean_params[param] = str(params[param])
        
        # Handle jobcode type
        if 'jobcode_type' in params:
            jobcode_type = str(params['jobcode_type']).lower()
            if jobcode_type not in ['regular', 'pto', 'paid_break', 'unpaid_break']:
                raise ValueError(f"jobcode_type must be one of: regular, pto, paid_break, unpaid_break")
            clean_params['jobcode_type'] = jobcode_type
        
        # Handle boolean parameters
        if 'include_zero_time' in params:
            clean_params['include_zero_time'] = str(bool(params['include_zero_time'])).lower()
        
        return self.make_request('payroll_by_jobcode', params=clean_params) # Should be self.make_request from BaseAPI for GET

    def get_project_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed project report with time tracking data.
        
        Args:
            params: Dictionary containing the following parameters:
                Required:
                    - start_date: Start date in YYYY-MM-DD format
                    - end_date: End date in YYYY-MM-DD format
                Optional:
                    - user_ids: List of user IDs to filter by
                    - group_ids: List of group IDs to filter by
                    - jobcode_ids: List of jobcode IDs to filter by
                    - jobcode_type: Filter by type ('regular', 'pto', 'unpaid_break', 'paid_break', 'all')
                    - customfielditems: Dict mapping custom field IDs to lists of values
        
        Returns:
            API response containing the project report data
        """
        # Create a copy of params to avoid modifying the original
        data_payload = params.copy() # Renamed to data_payload for clarity
        
        # Convert array parameters to proper format for the API if they are lists
        # The API for project report might expect lists directly for these fields in the POST body
        # For consistency with other methods, we'll ensure they are at least stringified if not lists.
        # However, the original code for this method seemed to imply lists are fine.
        # Let's stick to the pattern of converting to comma-separated strings if they are lists,
        # unless the API strictly requires lists for POST bodies for this specific endpoint.
        # Re-evaluating: The API docs for POST usually specify if lists are passed directly or as CSV.
        # For reports/project, it's a POST, and 'data' is the JSON body.
        # The example shows "user_ids": [123, 456]. So lists are fine.
        
        # Handle custom fields: ensure values are lists
        if 'customfielditems' in data_payload:
            if not isinstance(data_payload['customfielditems'], dict):
                raise ValueError("customfielditems must be a dictionary")
            for field_id, values in data_payload['customfielditems'].items():
                if not isinstance(values, list):
                    data_payload['customfielditems'][field_id] = [values]
        
        # Ensure dates are in YYYY-MM-DD format
        for date_field in ['start_date', 'end_date']:
            if date_field not in data_payload:
                raise ValueError(f"Missing required field: {date_field}")
            try:
                datetime.strptime(data_payload[date_field], '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid date format for {date_field}. Expected YYYY-MM-DD")
        
        # Make POST request with data_payload wrapped in a 'data' key
        return self.make_request('reports/project', method='POST', data={'data': data_payload})
        
    # This make_request was specific to ReportsAPI and is now part of BaseAPI
    # def make_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None):
    #     """Make a request to the QuickBooks Time API.
        
    #     Args:
    #         endpoint: API endpoint to call
    #         method: HTTP method ('GET' or 'POST')
    #         params: Query parameters for GET requests
    #         data: JSON data for POST requests
    #     """
    #     try:
    #         url = f'{self.base_url}/{endpoint}'
            
    #         if method.upper() == 'GET':
    #             response = requests.get(url, headers=self.headers, params=params)
    #         elif method.upper() == 'POST':
    #             response = requests.post(url, headers=self.headers, json=data)
    #         else:
    #             raise ValueError(f"Unsupported HTTP method: {method}")
                
    #         response.raise_for_status()
    #         return response.json()
    #     except Exception as error:
    #         return self.handle_axios_error(error, f'{method} request to {endpoint}')

class CustomFieldsAPI(BaseAPI):
    """API class for managing custom fields in QuickBooks Time."""
    
    def get_custom_fields(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get custom fields with optional filters.
        
        Args:
            params: Dictionary containing any of the following optional filters:
                - ids: List of custom field IDs to filter results
                - active: Filter by active status ('yes', 'no', 'both', default: 'yes')
                - applies_to: Filter by object type ('timesheet', 'user', 'jobcode')
                - value_type: Filter by field value type ('managed-list', 'free-form')
        
        Returns:
            Dict containing custom fields information
        """
        clean_params = self.add_pagination_params(params)
        return self.make_request('customfields', params=clean_params)

class QuickBooksTimeAPI(BaseAPI):
    def __init__(self, access_token: str):
        super().__init__(access_token)
        self.jobcode_api = JobcodeAPI(access_token)
        self.timesheet_api = TimesheetAPI(access_token)
        self.user_api = UserAPI(access_token)
        self.custom_fields_api = CustomFieldsAPI(access_token)
        self.project_management_api = ProjectManagementAPI(access_token)
        self.last_modified_api = LastModifiedAPI(access_token)
        self.notifications_api = NotificationsAPI(access_token)
        self.additional_features_api = AdditionalFeaturesAPI(access_token)
        self.reports_api = ReportsAPI(access_token)
        self.validate_token()

    def validate_token(self) -> bool:
        try:
            response = requests.get(
                f'{self.base_url}/current_user',
                headers=self.headers
            )
            response.raise_for_status()
            log_info('Token validation successful')
            return True
        except requests.exceptions.RequestException as error:
            if error.response is not None:
                error_message = ""
                try:
                    error_message = error.response.json().get('error', {}).get('message') or error.response.reason
                except requests.exceptions.JSONDecodeError:
                    error_message = error.response.reason
                raise ValueError(f'Token validation failed: {error.response.status_code} - {error_message}')
            elif error.request is not None:
                raise ValueError('Token validation failed: No response received from server')
            else:
                raise ValueError(f'Token validation failed: {str(error)}')

    def get_jobcodes(self, params: Optional[Dict[str, Any]] = None):
        return self.jobcode_api.get_jobcodes(params)

    def get_jobcode(self, params: Dict[str, Any]): # Changed to accept dict
        return self.jobcode_api.get_jobcode(params) # Pass dict directly

    # Assuming search_jobcodes was a typo and meant get_jobcodes or similar,
    # or it's a method that needs to be defined in JobcodeAPI.
    # For now, commenting out as it's not defined.
    # def search_jobcodes(self, params: Dict[str, Any]):
    #     return self.jobcode_api.search_jobcodes(params)

    def get_jobcode_hierarchy(self, params: Optional[Dict[str, Any]] = None):
        return self.jobcode_api.get_jobcode_hierarchy(params)

    def get_timesheets(self, params: Optional[Dict[str, Any]] = None):
        return self.timesheet_api.get_timesheets(params)

    def get_timesheet(self, params: Dict[str, Any]): # Changed to accept dict
        return self.timesheet_api.get_timesheet(params) # Pass dict directly

    def get_current_timesheets(self, params: Optional[Dict[str, Any]] = None):
        return self.timesheet_api.get_current_timesheets(params)

    def get_users(self, params: Optional[Dict[str, Any]] = None):
        return self.user_api.get_users(params)

    def get_user(self, params: Dict[str, Any]):
        return self.user_api.get_user(params)

    def get_current_user(self, params: Optional[Dict[str, Any]] = None): # params often not used here
        return self.user_api.get_current_user()

    def get_groups(self, params: Optional[Dict[str, Any]] = None):
        return self.user_api.get_groups(params)

    def get_custom_fields(self, params: Optional[Dict[str, Any]] = None):
        # Assuming this was meant to call the CustomFieldsAPI instance
        return self.custom_fields_api.get_custom_fields(params)

    def get_projects(self, params: Optional[Dict[str, Any]] = None):
        return self.project_management_api.get_projects(params)

    def get_project_activities(self, params: Optional[Dict[str, Any]] = None):
        return self.project_management_api.get_project_activities(params)

    def get_last_modified(self, params: Optional[Dict[str, Any]] = None):
        types_list = None
        if params and 'types' in params: # Ensure params and 'types' key exist
            types_list = params.get('types')
        return self.last_modified_api.get_last_modified(types_list)


    def get_notifications(self, params: Optional[Dict[str, Any]] = None):
        return self.notifications_api.get_notifications(params)

    def get_managed_clients(self, params: Optional[Dict[str, Any]] = None):
        return self.additional_features_api.get_managed_clients(params)

    def get_current_totals(self, params: Optional[Dict[str, Any]] = None):
        return self.reports_api.get_current_totals(params)

    def get_payroll(self, params: Dict[str, Any]):
        return self.reports_api.get_payroll(params)

    def get_payroll_by_jobcode(self, params: Dict[str, Any]):
        return self.reports_api.get_payroll_by_jobcode(params)

    def get_project_report(self, params: Dict[str, Any]):
        return self.reports_api.get_project_report(params)
