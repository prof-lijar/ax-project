# Background workers

`weekly_report.py` is the independently scalable, durable execution boundary
for high-volume weekly-report exports. PostgreSQL leases coordinate a single
paged producer, bounded asynchronous consumers, and a recoverable finalizer.
Workers can be replicated on hosts that share the job database and private
artifact volume.

The worker does not expose an HTTP port, schedule jobs, or send Slack messages.
`apps/weekly_report_bulk_api` is the separate private operator control plane for
submission, content-free status, cancellation, and verified export download.
The default development UI reaches that API through the Vite proxy. See the
weekly-report implementation specification for UI and CLI operation, cleanup,
capacity evaluation, and remaining benchmark gates.
