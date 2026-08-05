# Background workers

This deployment boundary is reserved for long-running and asynchronous graph
execution when API and queue workloads need independent scaling. Agent Server
single-host mode remains the initial baseline; do not create a custom worker
loop until measurements justify split API/queue deployment.
