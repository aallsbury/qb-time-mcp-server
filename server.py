import json
import sys
import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from api import QuickBooksTimeAPI
from utils import setup_logging, log_info, log_error

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"

SERVER_INFO = {
    "name": "qb-time-tools",
    "version": "1.0.0",
    "vendor": "QuickBooks Time API Client",
    "description": "Access QuickBooks Time data through these API tools.",
    "tools": [
        {
            "name": "get_jobcodes",
            "description": "Get jobcodes from QuickBooks Time with advanced filtering options. Returns jobcode details including name, type, and status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "number"}, "description": "Filter by specific jobcode IDs"},
                    "parent_ids": {"type": "array", "items": {"type": "number"}, "description": "Filter by parent jobcode IDs"},
                    "name": {"type": "string", "description": "Filter by name (use * as wildcard)"},
                    "type": {"type": "string", "enum": ["regular", "pto", "paid_break", "unpaid_break", "all"], "description": "Filter by jobcode type"},
                    "active": {"type": "string", "enum": ["yes", "no", "both"], "description": "Filter by active status"},
                    "customfields": {"type": "boolean", "description": "Include custom field data"},
                    "modified_before": {"type": "string", "description": "Return items modified before this date"},
                    "modified_since": {"type": "string", "description": "Return items modified after this date"},
                    "supplemental_data": {"type": "string", "enum": ["yes", "no"], "description": "Include supplemental data"},
                    "page": {"type": "number", "description": "Page number for pagination"},
                    "limit": {"type": "number", "description": "Number of results per page (max 200)"}
                }
            }
        },
        {
            "name": "get_jobcode",
            "description": "Get detailed information about a specific jobcode including its properties, hierarchy position, billing settings, and optional custom fields.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "number",
                        "description": "The unique identifier of the jobcode to retrieve"
                    },
                    "customfields": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include custom fields in response"
                    }
                },
                "required": ["id"]
            }
        },
        {
            "name": "get_jobcode_hierarchy",
            "description": "Get the hierarchical structure of jobcodes in your company. Jobcodes can be organized in a parent-child relationship, creating a tree-like structure.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter by parent IDs. Special values: 0 (top-level only), -1 (all levels). Default returns all levels."
                    },
                    "active": {
                        "type": "string",
                        "enum": ["yes", "no", "both"],
                        "default": "yes",
                        "description": "Filter by active status"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["regular", "pto", "paid_break", "unpaid_break", "all"],
                        "default": "regular",
                        "description": "Filter by jobcode type"
                    }
                }
            }
        },
        {
            "name": "get_timesheets",
            "description": "Get timesheets from QuickBooks Time.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "modified_before": {"type": "string"},
                    "modified_since": {"type": "string"},
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "get_timesheet",
            "description": "Get a specific timesheet by ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "number", "description": "The ID of the timesheet to retrieve"}
                },
                "required": ["id"]
            }
        },
        {
            "name": "get_current_timesheets",
            "description": "Get currently active timesheets (users who are 'on the clock') with filtering options.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter active timesheets for specific users"
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter active timesheets for users in specific groups"
                    },
                    "jobcode_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter active timesheets for specific jobcodes"
                    },
                    "supplemental_data": {
                        "type": "string",
                        "enum": ["yes", "no"],
                        "default": "yes",
                        "description": "Include supplemental data (users, jobcodes) in response"
                    }
                }
            }
        },
        {
            "name": "get_users",
            "description": "Get users from QuickBooks Time with advanced filtering options.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter by specific user IDs"
                    },
                    "not_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Exclude specific user IDs"
                    },
                    "employee_numbers": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter by employee numbers"
                    },
                    "usernames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by specific usernames"
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter users by their group membership"
                    },
                    "not_group_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Exclude users from specific groups"
                    },
                    "payroll_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by payroll identification numbers"
                    },
                    "active": {
                        "type": "string",
                        "enum": ["yes", "no", "both"],
                        "default": "yes",
                        "description": "Filter by user status"
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Filter by first name"
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Filter by last name"
                    },
                    "modified_before": {
                        "type": "string",
                        "description": "Only users modified before this date/time (ISO 8601 format)"
                    },
                    "modified_since": {
                        "type": "string",
                        "description": "Only users modified since this date/time (ISO 8601 format)"
                    },
                    "page": {
                        "type": "number",
                        "description": "Page number for pagination"
                    },
                    "per_page": {
                        "type": "number",
                        "description": "Number of results per page (max 200)"
                    }
                }
            }
        },
        {
            "name": "get_user",
            "description": "Get user details from QuickBooks Time with advanced filtering options.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter by specific user IDs"
                    },
                    "active": {
                        "type": "string",
                        "enum": ["yes", "no"],
                        "description": "Filter by active or inactive users"
                    },
                    "first_name": {
                        "type": "string",
                        "description": "Filter by first name"
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Filter by last name"
                    },
                    "modified_before": {
                        "type": "string",
                        "description": "Only users modified before this date/time (ISO 8601 format)"
                    },
                    "modified_since": {
                        "type": "string",
                        "description": "Only users modified since this date/time (ISO 8601 format)"
                    },
                    "page": {
                        "type": "number",
                        "description": "Page number to return"
                    },
                    "per_page": {
                        "type": "number",
                        "description": "Number of results per page"
                    },
                    "payroll_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by payroll IDs"
                    }
                }
            }
        },
        {
            "name": "get_current_user",
            "description": "Get detailed information about the currently authenticated user, including permissions, PTO balances, and custom field values.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        },
        {
            "name": "get_groups",
            "description": "Get information about groups in your company, used for organizing users and managing permissions at a group level.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter results to specific group IDs"
                    },
                    "active": {
                        "type": "string",
                        "enum": ["yes", "no", "both"],
                        "default": "yes",
                        "description": "Filter by active status"
                    },
                    "manager_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter groups by manager user IDs"
                    },
                    "supplemental_data": {
                        "type": "string",
                        "enum": ["yes", "no"],
                        "default": "yes",
                        "description": "Include supplemental data (manager details) in response"
                    }
                }
            }
        },
        {
            "name": "get_custom_fields",
            "description": "Get custom fields configured in your company for tracking additional information on timesheets and other objects.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter results to specific custom field IDs"
                    },
                    "active": {
                        "type": "string",
                        "enum": ["yes", "no", "both"],
                        "default": "yes",
                        "description": "Filter by active status"
                    },
                    "applies_to": {
                        "type": "string",
                        "enum": ["timesheet", "user", "jobcode"],
                        "description": "Filter by applicable object type"
                    },
                    "value_type": {
                        "type": "string",
                        "enum": ["managed-list", "free-form"],
                        "description": "Filter by field value type"
                    }
                }
            }
        },
        {
            "name": "get_projects",
            "description": "Get projects from QuickBooks Time.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "modified_before": {"type": "string"},
                    "modified_since": {"type": "string"},
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "get_project_activities",
            "description": "Get project activities.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "get_last_modified",
            "description": "Get last modified timestamps for objects.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "types": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        {
            "name": "get_notifications",
            "description": "Get notifications.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "get_managed_clients",
            "description": "Get managed clients.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                }
            }
        },
        {
            "name": "get_current_totals",
            "description": "Get real-time totals for currently active time entries, with filtering options.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional array of integers. Filter totals to specific users"
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional array of integers. Filter totals for users in specific groups"
                    },
                    "on_the_clock": {
                        "type": "string",
                        "description": "Optional string. Filters users based on clock status (e.g., 'yes', 'no', 'both')."
                    },
                    "page": {
                        "type": "integer",
                        "description": "Optional integer. Page number for pagination."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional integer. Number of results per page for pagination, with a default and max."
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Optional string. Orders results by specified field (e.g., 'username', 'first_name', etc.)."
                    },
                    "order_desc": {
                        "type": "boolean",
                        "description": "Optional boolean. Orders results descending when true."
                    }
                }
            }
        },
        {
            "name": "get_payroll",
            "description": "Get payroll report.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                },
                "required": ["start_date", "end_date"]
            }
        },
        {
            "name": "get_payroll_by_jobcode",
            "description": "Get payroll report grouped by jobcode.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "page": {"type": "number"},
                    "limit": {"type": "number"}
                },
                "required": ["start_date", "end_date"]
            }
        },
        {
            "name": "get_project_report",
            "description": "Get detailed project report with time tracking data and advanced filtering options.",
            "inputSchema": {
                "type": "object",
                "required": ["start_date", "end_date"],
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format. Any time entries on or after this date will be included."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format. Any time entries on or before this date will be included."
                    },
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter time entries by specific users"
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter time entries by specific groups"
                    },
                    "jobcode_ids": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Filter time entries by specific jobcodes"
                    },
                    "jobcode_type": {
                        "type": "string",
                        "enum": ["regular", "pto", "unpaid_break", "paid_break", "all"],
                        "default": "all",
                        "description": "Filter by type of jobcodes"
                    },
                    "customfielditems": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "description": "Filter by custom field values. Format: { 'customfield_id': ['value1', 'value2'] }"
                    }
                }
            }
        }
    ]
}

class JSONRPCServer:
    def __init__(self, access_token: str, node_env: str):
        self.api = QuickBooksTimeAPI(access_token)
        self.node_env = node_env
        self.message_buffer = ''
        self.message_counter = 0
        setup_logging()

    def get_next_id(self) -> str:
        self.message_counter += 1
        return str(self.message_counter)

    def send_response(self, response: dict):
        response_str = json.dumps(response)
        sys.stdout.write(response_str + '\n')
        sys.stdout.flush()

    def send_error_response(self, id: str, code: int, message: str, data=None):
        self.send_response({
            'jsonrpc': JSONRPC_VERSION,
            'id': id,
            'error': {
                'code': code,
                'message': message,
                'data': data
            }
        })

    def handle_initialize(self, message: dict):
        if 'id' not in message:
            self.send_error_response(self.get_next_id(), -32600, 'Initialize must include an id')
            return

        self.send_response({
            'jsonrpc': JSONRPC_VERSION,
            'id': message['id'],
            'result': {
                'protocolVersion': PROTOCOL_VERSION,
                'capabilities': {
                    'tools': {
                        'listChanged': True
                    }
                },
                'serverInfo': SERVER_INFO
            }
        })

    def handle_ping(self, message: dict):
        """Handle ping requests from LibreChat for health checking"""
        if 'id' not in message:
            self.send_error_response(self.get_next_id(), -32600, 'Ping request must include an id')
            return

        log_info('Received ping request - responding with MCP-compliant empty result')
        self.send_response({
            'jsonrpc': JSONRPC_VERSION,
            'id': message['id'],
            'result': {}
        })

    def handle_tools_list(self, message: dict):
        if 'id' not in message:
            self.send_error_response(self.get_next_id(), -32600, 'Tools list request must include an id')
            return

        self.send_response({
            'jsonrpc': JSONRPC_VERSION,
            'id': message['id'],
            'result': {
                'tools': SERVER_INFO['tools']
            }
        })

    def handle_tools_call(self, message: dict):
        if 'id' not in message:
            self.send_error_response(self.get_next_id(), -32600, 'Tools call must include an id')
            return

        params = message.get('params', {})
        name = params.get('name')
        args = params.get('arguments', {})

        if not name or not isinstance(args, dict):
            self.send_error_response(message['id'], -32602, 'Invalid params: must include name and arguments')
            return

        method_map = {
            'get_jobcodes': self.api.get_jobcodes,
            'get_jobcode': self.api.get_jobcode,
            'get_jobcode_hierarchy': self.api.get_jobcode_hierarchy,
            'get_timesheets': self.api.get_timesheets,
            'get_timesheet': self.api.get_timesheet,
            'get_current_timesheets': self.api.get_current_timesheets,
            'get_users': self.api.get_users,
            'get_user': self.api.get_user,
            'get_current_user': self.api.get_current_user,
            'get_groups': self.api.get_groups,
            'get_custom_fields': self.api.get_custom_fields,
            'get_projects': self.api.get_projects,
            'get_project_activities': self.api.get_project_activities,
            'get_last_modified': self.api.get_last_modified,
            'get_notifications': self.api.get_notifications,
            'get_managed_clients': self.api.get_managed_clients,
            'get_current_totals': self.api.get_current_totals,
            'get_payroll': self.api.get_payroll,
            'get_payroll_by_jobcode': self.api.get_payroll_by_jobcode,
            'get_project_report': self.api.get_project_report
        }

        if name not in method_map:
            self.send_error_response(message['id'], -32601, f'Unknown method: {name}')
            return

        try:
            result = method_map[name](args)
            self.send_response({
                'jsonrpc': JSONRPC_VERSION,
                'id': message['id'],
                'result': {
                    'content': [{
                        'type': 'text',
                        'text': json.dumps(result)
                    }]
                }
            })
        except Exception as e:
            log_error(f'Error in {name}: {str(e)}')
            self.send_error_response(message['id'], -32000, str(e))

    def handle_message(self, message_str: str):
        message_id = self.get_next_id()

        try:
            message = json.loads(message_str)

            if 'method' not in message:
                self.send_error_response(
                    message.get('id', message_id),
                    -32600,
                    'Invalid Request'
                )
                return

            if message['method'] == 'initialize':
                self.handle_initialize(message)
            elif message['method'] == 'ping':
                self.handle_ping(message)
            elif message['method'] == 'tools/list':
                self.handle_tools_list(message)
            elif message['method'] == 'tools/call':
                self.handle_tools_call(message)
            else:
                if 'id' in message:
                    self.send_error_response(message['id'], -32601, 'Method not found')
                else:
                    log_info(f'Received notification for method: {message["method"]}')

        except json.JSONDecodeError:
            self.send_error_response(message_id, -32700, 'Parse error')

    def send_server_info(self):
        self.send_response({
            'jsonrpc': JSONRPC_VERSION,
            'method': 'server/info',
            'params': {
                'serverInfo': SERVER_INFO
            }
        })

    def start(self):
        log_info('QuickBooks Time MCP Server Starting')
        log_info(f'Environment: {{"tokenConfigured": {bool(self.api.access_token)}, "nodeEnv": "{self.node_env}"}}')

        # Send initial server info
        self.send_server_info()

        # Start reading from stdin
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                self.handle_message(line.strip())
            except KeyboardInterrupt:
                log_info('Server shutting down.')
                break

def run_server(access_token: str, node_env: str = 'development'):
    server = JSONRPCServer(access_token, node_env)
    server.start()

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    access_token = os.getenv('QB_TIME_ACCESS_TOKEN')
    node_env = os.getenv('NODE_ENV', 'development')

    if not access_token:
        print("QB_TIME_ACCESS_TOKEN environment variable is required")
        sys.exit(1)

    run_server(access_token, node_env)
