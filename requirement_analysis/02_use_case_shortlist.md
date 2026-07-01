# AX Use Case Shortlist

## Selection Criteria

Use cases should be selected based on:

- Clear business or operational value.
- Access to required data.
- Low risk for the first pilot.
- Ability to keep sensitive data local.
- Measurable result within a short pilot period.
- Human approval path for important actions.

## Suggested Use Cases

| Use Case | Description | Main Users | AI Role | Priority |
| --- | --- | --- | --- | --- |
| Internal knowledge Q&A | Search and answer questions from project docs, specs, manuals, and notes. | Staff, PM, support | RAG assistant | High |
| Document summary and extraction | Summarize PDFs, reports, meeting notes, contracts, and project documents. | PM, operations, sales | Extraction and summarization agent | High |
| Workflow status assistant | Query project or service status and prepare short updates. | PM, operations | Data lookup and reporting agent | High |
| Alert triage assistant | Analyze alerts, classify severity, suggest response steps, and draft notifications. | Operations, support | Triage and recommendation agent | High |
| Report generation | Generate internal reports from service data, satisfaction results, logs, and notes. | PM, management | Report agent | Medium |
| Development support agent | Review code changes, summarize issues, draft fixes, and assist with service extension work. | Developers | Coding and review agent | Medium |
| Customer or caregiver support assistant | Draft answers and guidance based on approved service documents. | Support team | Human-approved response assistant | Medium |
| Batch research and analysis | Run parallel research, comparison, or data analysis jobs. | Strategy, PM | Batch worker agents | Medium |

## Candidate Pilot: 안심지키미 Smart Care Service

The provided `안심지키미` satisfaction result image suggests a practical AX pilot around smart care service operations.

### Relevant Observations

- Overall satisfaction shown: 4.70 out of 5.
- Positive response shown: 95.6%.
- Subscriber score shown: 4.65.
- Caregiver score shown: 4.73.
- Strong perceived effects:
  - Continued service usage intention.
  - Device convenience.
  - Emergency response support.
  - Privacy-preserving, non-video care.
  - Reduced caregiver burden.
- Improvement directions shown:
  - Clarify risk alert guidance and response procedures.
  - Add or strengthen exception management for hospital admission or long absence.

### Suggested AI Extensions

- Alert explanation assistant: explain why an alert happened and suggest next response steps.
- Caregiver summary assistant: provide short, approved status summaries without exposing unnecessary sensitive data.
- Exception management assistant: detect long absence, hospital admission notes, or unusual patterns and request confirmation.
- Service report assistant: generate monthly service reports and satisfaction summaries.
- Operations knowledge assistant: answer staff questions from manuals, service rules, and past reports.

## Recommended First Pilot

Start with a controlled RAG and workflow assistant before autonomous action.

Suggested pilot:

> AX Operations Assistant for one existing service, preferably `안심지키미` if the related data, manuals, and operational workflows are available.

Initial scope:

- Search approved documents.
- Summarize service status.
- Draft alert response guidance.
- Draft reports.
- Log every request, source, output, and human approval decision.

Out of scope for the first pilot:

- Direct production actions without approval.
- Automated customer or caregiver messages without review.
- Unrestricted database access.
- Code deployment or production changes.

