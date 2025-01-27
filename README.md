# QuickBooks Time MCP Server (V2 Update)
[![smithery badge](https://smithery.ai/badge/qb-time-mcp-server)](https://smithery.ai/server/qb-time-mcp-server)

This is a combined MCP server that provides access to all QuickBooks Time API functionality through a single interface. It combines the functionality of four separate servers:

1. JobCode Tools
2. Reports & Core Tools
3. Timesheet Tools
4. User Tools

I would LOVE help improving this project! Just glad to be able to give something back finally!

This entire project was developed and published using artificial intelligence (Anthropic, OpenAI, Llama/META), as I personally cannot write much code without assistance. While every effort has been made to ensure quality and functionality, there may be imperfections or areas for improvement. I welcome any feedback, corrections, or suggestions from the community.

### Installing via Smithery

To install QuickBooks Time MCP Server for Claude Desktop automatically via [Smithery](https://smithery.ai/server/qb-time-mcp-server):

```bash
npx -y @smithery/cli install qb-time-mcp-server --client claude
```

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your QuickBooks Time access token:
```
QB_TIME_ACCESS_TOKEN=your_access_token_here
NODE_ENV=development
```

## Claude Desktop Configuration

To use this server with Claude Desktop, you'll need to configure it in your Claude Desktop settings. Here's an example configuration:

```json
{
  "globalShortcut": "Ctrl+Q",
  "mcpServers": {
    "qb-time-tools": {
      "command": "python",
      "args": [
        "./qb-time-mcp-server/main.py"
      ],
      "env": {
        "QB_TIME_ACCESS_TOKEN": "your_quickbooks_time_access_token_here"
      }
    }
  }
}
```

## Available Tools

### JobCode Tools
- `get_jobcodes`: Get jobcodes with advanced filtering options
  - Basic Filters:
    - `ids`: (array of numbers, optional) Comma separated list of jobcode IDs
    - `name`: (string, optional) Filter by jobcode name, supports wildcard (*) matching from string start
    - `active`: (string, optional) Filter by status: "yes", "no", "both" (default: "yes")
  - Type and Hierarchy Filters:
    - `type`: (string, optional) Filter by type: "regular", "pto", "paid_break", "unpaid_break", "all" (default: "regular")
    - `parent_ids`: (array of numbers, optional) Filter by parent jobcode IDs. Special values: 0 (top-level only), -1 (all levels)
  - Additional Filters:
    - `customfields`: (boolean, optional) Include custom fields in response
    - `modified_before`: (string, optional) Filter by modification date (ISO 8601 format)
    - `modified_since`: (string, optional) Filter by modification date (ISO 8601 format)
    - `page`: (number) Page number for pagination
    - `limit`: (number) Results per page (max 200)

- `get_jobcode`: Get a specific jobcode by ID
  - Required Parameters:
    - `id`: (number) The ID of the jobcode to retrieve

- `get_jobcode_hierarchy`: Get complete jobcode hierarchy structure
  - Parameters:
    - `parent_ids`: (array of numbers, optional) Filter by parent IDs. Values: 0 (top-level), -1 (all), or specific IDs
    - `active`: (string, optional) Filter by status: "yes", "no", "both" (default: "yes")
    - `type`: (string, optional) Filter by type: "regular", "pto", "paid_break", "unpaid_break", "all" (default: "regular")
    - `customfields`: (boolean, optional) Include custom fields in response

### Timesheet Tools
- `get_timesheets`: Get timesheets with filtering
  - Required Parameters (at least one):
    - `ids`: (array of numbers) Comma separated list of timesheet IDs
    - `start_date`: (string) Returns timesheets on or after this date (YYYY-MM-DD)
    - `modified_before`: (string) Returns timesheets modified before this time (ISO 8601)
    - `modified_since`: (string) Returns timesheets modified since this time (ISO 8601)
  - Optional Parameters:
    - `end_date`: (string) Returns timesheets on or before this date (YYYY-MM-DD)
    - `user_ids`: (array of numbers) Filter by specific user IDs
    - `group_ids`: (array of numbers) Filter by specific group IDs
    - `jobcode_ids`: (array of numbers) Filter by specific jobcode IDs (includes children)
    - `payroll_ids`: (array of numbers) Filter by specific payroll IDs
    - `on_the_clock`: (string) Filter by current working status: "yes", "no", "both" (default: "no")
    - `jobcode_type`: (string) Filter by type: "regular", "pto", "paid_break", "unpaid_break", "all" (default: "all")
    - `page`: (number) Page number
    - `limit`: (number) Results per page

- `get_timesheet`: Get a specific timesheet by ID
  - Required Parameters:
    - `id`: (number) The ID of the timesheet to retrieve

- `get_current_timesheets`: Get currently active timesheets
  - Required Parameters:
    - `on_the_clock`: (string) Must be set to "yes"
  - Optional Parameters:
    - `user_ids`: (array of numbers) Filter active timesheets for specific users
    - `group_ids`: (array of numbers) Filter active timesheets for users in specific groups
    - `jobcode_ids`: (array of numbers) Filter active timesheets for specific jobcodes
    - `supplemental_data`: (string) Include supplemental data: "yes", "no" (default: "yes")

### User Tools
- `get_users`: Get all users with filtering
  - User Identification Filters:
    - `ids`: (array of numbers, optional) Filter by specific user IDs
    - `not_ids`: (array of numbers, optional) Exclude specific user IDs
    - `employee_numbers`: (array of numbers, optional) Filter by employee numbers
    - `usernames`: (array of strings, optional) Filter by specific usernames
  - Group Filters:
    - `group_ids`: (array of numbers, optional) Filter by group membership
    - `not_group_ids`: (array of numbers, optional) Exclude users from specific groups
  - Status and Identification Filters:
    - `payroll_ids`: (array of strings, optional) Filter by payroll identification numbers
    - `active`: (string, optional) Filter by status: "yes", "no", "both" (default: "yes")
  - Name Filters:
    - `first_name`: (string, optional) Filter by first name (supports wildcards *)
    - `last_name`: (string, optional) Filter by last name (supports wildcards *)
  - Time-Based Filters:
    - `modified_before`: (string, optional) Filter by modification date (ISO 8601)
    - `modified_since`: (string, optional) Filter by modification date (ISO 8601)
  - Pagination:
    - `page`: (number, optional) Page number (default: 1)
    - `per_page`: (number, optional) Results per page (default: 50, max: 50)

- `get_user`: Get a specific user by ID
  - Required Parameters:
    - `id`: (number) The ID of the user to retrieve

- `get_current_user`: Get currently authenticated user
  - No parameters required
  - Returns detailed user information including:
    - Basic profile information
    - Company details
    - PTO balances
    - Permissions
    - Custom fields

- `get_groups`: Get all groups from QuickBooks Time
  - Optional Parameters:
    - `ids`: (array of numbers) Filter by specific group IDs
    - `active`: (string) Filter by status: "yes", "no", "both" (default: "yes")
    - `manager_ids`: (array of numbers) Filter groups by manager user IDs
    - `supplemental_data`: (string) Include supplemental data: "yes", "no" (default: "yes")
  - Returns group information including:
    - Basic group details
    - Manager assignments
    - Timesheet settings
    - Time entry settings
    - Break settings

### Project Management Tools
- `get_projects`: Get projects with filtering
  - Optional Parameters:
    - `ids`: (array of numbers) Filter by specific project IDs
    - `active`: (string) Filter by status: "yes", "no", "both" (default: "yes")
    - `client_id`: (number) Filter by client ID
    - `jobcode_id`: (number) Filter by associated jobcode ID
    - `modified_before`: (string) Filter by modification date (ISO 8601)
    - `modified_since`: (string) Filter by modification date (ISO 8601)
    - `page`: (number) Page number (default: 1)
    - `per_page`: (number) Results per page (default: 50, max: 50)
  - Returns project information including:
    - Basic project details
    - Client and jobcode associations
    - Budget information
    - Dates and status
    - Custom fields

- `get_project_activities`: Get project activity logs
  - Optional Parameters:
    - `project_ids`: (array of numbers) Filter activities to specific projects
    - `user_ids`: (array of numbers) Filter activities by specific users
    - `activity_types`: (array of strings) Filter by activity types: "status_change", "note_added", "budget_change", "date_change", "custom_field_change"
    - `modified_before`: (string) Filter by modification date (ISO 8601)
    - `modified_since`: (string) Filter by modification date (ISO 8601)
    - `page`: (number) Page number (default: 1)
    - `per_page`: (number) Results per page (default: 50, max: 50)
  - Returns activity information including:
    - Activity type and details
    - User who made the change
    - Old and new values
    - Timestamps

### Reports Tools
- `get_current_totals`: Get current totals snapshot including shift and day totals
  - Optional Parameters:
    - `user_ids`: (array of numbers) Filter totals to specific users
    - `group_ids`: (array of numbers) Filter totals for users in specific groups
    - `jobcode_ids`: (array of numbers) Filter totals for specific jobcodes
    - `customfield_query`: (string) Filter by custom field values in format: <customfield_id>|<op>|<value>
  - Returns:
    - Real-time totals for active time entries
    - Duration and start times
    - Associated jobcode and user information
    - Custom field values

- `get_payroll`: Get payroll report
  - Required Parameters:
    - `start_date`: (string) Start of pay period (YYYY-MM-DD)
    - `end_date`: (string) End of pay period (YYYY-MM-DD)
  - Optional Parameters:
    - `user_ids`: (array of numbers) Filter payroll for specific users
    - `group_ids`: (array of numbers) Filter payroll for users in specific groups
    - `include_zero_time`: (boolean) Include users with no time entries (default: false)
  - Returns:
    - Total time by type (regular, overtime, double-time, PTO)
    - Daily breakdowns per user
    - Timesheet counts

- `get_payroll_by_jobcode`: Get payroll report grouped by jobcode
  - Required Parameters:
    - `start_date`: (string) Start of pay period (YYYY-MM-DD)
    - `end_date`: (string) End of pay period (YYYY-MM-DD)
  - Optional Parameters:
    - `user_ids`: (array of numbers) Filter payroll for specific users
    - `group_ids`: (array of numbers) Filter payroll for users in specific groups
    - `jobcode_ids`: (array of numbers) Filter payroll for specific jobcodes
    - `jobcode_type`: (string) Filter by type: "regular", "pto", "paid_break", "unpaid_break"
    - `include_zero_time`: (boolean) Include jobcodes with no time entries (default: false)
  - Returns:
    - Time totals by jobcode
    - Breakdowns by user within each jobcode
    - Daily totals per jobcode

- `get_project_report`: Get detailed project report with time entries
  - Required Parameters:
    - `start_date`: (string) Start date in YYYY-MM-DD format
    - `end_date`: (string) End date in YYYY-MM-DD format
  - Optional Parameters:
    - `user_ids`: (array of numbers) Filter time entries by specific users
    - `group_ids`: (array of numbers) Filter time entries by specific groups
    - `jobcode_ids`: (array of numbers) Filter time entries by specific jobcodes
    - `jobcode_type`: (string) Filter by type: "regular", "pto", "unpaid_break", "paid_break", "all" (default: "all")
    - `customfielditems`: (object) Filter by custom field values in format: {"customfield_id": ["value1", "value2"]}
  - Returns:
    - Project time totals
    - Breakdowns by user and group
    - Filtered time entries based on criteria

### Additional Tools
- `get_custom_fields`: Get custom tracking fields configured on timecards
  - Parameters:
    - `ids`: (array of numbers) Filter by specific custom field IDs
    - `active`: (string) Filter by status: "yes", "no", "both"
    - `applies_to`: (string) Filter by application type: "timesheet", "jobcode", "user"
    - `value_type`: (string) Filter by value type: "managed-list", "free-form"
    - `page`: (number) Page number
    - `limit`: (number) Results per page

- `get_last_modified`: Get last modified timestamps for objects
  - Parameters:
    - `types`: (array of strings) Types of objects to check (e.g., ["timesheets", "jobcodes", "users"])

- `get_notifications`: Get notifications
  - Parameters:
    - `page`: (number) Page number
    - `limit`: (number) Results per page

- `get_managed_clients`: Get managed clients
  - Parameters:
    - `page`: (number) Page number
    - `limit`: (number) Results per page

## Running the Server

```bash
python main.py
```

The server will start and listen for JSON-RPC requests on stdin/stdout.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Given that this project was developed with AI assistance, community input is especially valuable for improving and maintaining the codebase.

## Support

For issues and feature requests, please use the GitHub issues page or contact me directly at github.com/aallsbury.
