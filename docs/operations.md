# Reliable Windows startup

The stdio command remains `python main.py`. The 20 existing tool names, schemas
and successful result envelopes are recorded in
`tests/fixtures/deployed-tool-contract.json` and exercised through stdio and SSE.
The SSE paths remain `/sse` and `/message`; the deployment example uses port 9994.

## Configuration and dependencies

Install Python dependencies in a dedicated environment with
`python -m pip install -r requirements.lock`, then `python -m pip check`.
This lock records the tested Python 3.11 dependency set. It is a reproducibility
baseline, not a claim that every dependency is the latest release.

`main.py` loads the adjacent `.env` regardless of the current directory. Use
`--env-file C:\absolute\private\qbtime.env` for an explicit path. Existing process
environment values take precedence. Keep `QB_TIME_ACCESS_TOKEN` out of command
arguments, task XML, logs and Git. The token is required. The optional
`QBT_CONNECT_TIMEOUT_SECONDS` (default 5) and `QBT_READ_TIMEOUT_SECONDS` (default
30) must be finite positive numbers no greater than 120. Each HTTP response is
closed on success and failure. These are connection/read inactivity timeouts,
not a total deadline across every call in a tool.

`python main.py --env-file C:\absolute\private\qbtime.env --check-config` verifies
configuration and imports without constructing the API client, contacting
QuickBooks, or opening a listener. Normal server startup retains the existing
read-only token validation request to `current_user`.

Provision a separately locked, reviewed gateway runtime. The supervisor example
expects released supergateway 4.2.1. It uses one stdio child per SSE session and
closes that child with the session. Do not restore an unpinned `npx` startup.
The private deployment owns the exact Node dependency lock; no third-party
patched sources or deployment credentials belong in this repository.

## Supervisor and task installation

Copy `deploy/windows/qbtime.example.json` to a private path and replace every
account/path with actual values. The JSON must not contain credentials. Use a
stable release directory, a private existing environment file, the reviewed
gateway entry point/version and a writable private state directory. Restrict
the environment file and state directory to the operating account and
administrators with the normal deployment ACLs.

First run `python deploy/windows/supervisor.py --config C:\private\qbtime.json
--check`. This verifies paths, required release files and the gateway version;
it does not start the server. Run the independent `main.py --check-config` too.
`supervisor.py --config ...` is the explicit start command.

The supervisor requires the configured Windows account. It takes an exclusive
port-specific file lock, refuses a pre-existing listener, and places its own
launcher, gateway and descendants in a Windows Job Object. Closing or killing
the supervisor closes that job and terminates only the process tree it owns.
It never kills processes by executable name. Gateway startup uses explicit
absolute paths, hidden child windows and a known working directory.

Startup readiness uses initialize, ping and tools/list over SSE; it never invokes
a business tool. The released gateway starts a child for that session, whose
normal startup validates the token against `current_user`. Full readiness runs
every five minutes by default. Three consecutive failed established probes cause
recovery. A gateway process exit wakes supervision immediately, independently of
the five-minute probe interval. Startup has a bounded readiness window; five
consecutive unsuccessful starts use bounded 5/15/30/60-second backoff followed
by a five-minute cooldown. Retry batches continue so a long upstream outage can
recover without manual intervention. Ten stable minutes reset the failure count.
Invalid configuration, wrong account or duplicate ownership fails instead of
silently taking over. Task Scheduler also retries a failed supervisor up to three
times at five-minute intervals.

`Register-QBTimeTask.ps1 -ConfigPath C:\private\qbtime.json -Mode Logon` registers
a limited-user task for the configured user's next logon. `-WhatIf` previews
registration. It does not provide startup before logon. A true boot task uses
`-Mode Boot -Credential (Get-Credential 'HOSTNAME\service-user')`. It runs with
limited privileges; creating a startup trigger/password task may require an
elevated registration session or local task rights. Supply the credential
interactively and let Task Scheduler store it; never serialize it into JSON or
source. Do not use SYSTEM or highest privileges simply to bypass registration
permissions. The registration script refuses to overwrite an existing task and
never starts the task. Activation is a separate `Start-ScheduledTask` action.

The task uses the environment's `pythonw.exe` to avoid a visible console. The
supervisor launches its child using the configured `python.exe` so stdio remains
available. Existing interface binding is preserved; any restriction to loopback
must first be tested from every caller, including Docker.

## Logs, validation and rollback

The private state directory contains `status.json`, a lock file, and
`supervisor.log` with three rotated backups of at most 1 MB each. Logs contain
process identifiers, readiness state and exception/status categories. Gateway
request/result stdout goes directly to the null device, and child stderr is reduced to
metadata. Optional standalone `QBT_LOG_FILE` uses 2 MB rotation with three
backups; do not share it between concurrent server processes.

Run `python -m unittest discover -s tests -v`. Set `QBT_TEST_GATEWAY_ROOT` to the
separately installed gateway directory to include SSE integration. Without that
runtime, the SSE tests are skipped. Tests use synthetic API fixtures and ephemeral
ports; they do not load production credentials or invoke live business actions.
They check every existing tool contract, HTTP timeout/closure, malformed input,
exclusive ownership, owned-tree cleanup, repeated SSE sessions and concurrency.
The deployment must also verify its actual consumer's SDK against the synthetic
gateway before activation.

Deploy from a reviewed immutable release and preserve the prior source/config
and dependency locks. For rollback, stop and disable only this QBTime task,
verify its owned process tree exits, then restore the previous release/config.
The supervisor does not roll back application source or change other MCP servers.
After activation, check `status.json` and perform a tools/list handshake from the
consumer before resuming scheduled callers. A successful handshake proves the
interface/token check, not the correctness of every business operation.
