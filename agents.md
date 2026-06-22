# AX Project Working Notes

This file captures the working conventions for future AX Project tasks in this workspace. Keep outputs consistent, practical, and grounded in the information provided.

## Project Context

- Company: Nextor.ai
- Project: AX Project
- Purpose: identify and design practical ways to integrate AI into current applications, workflows, and internal operations.
- Typical inputs: hardware photos, infrastructure notes, application lists, workflow examples, and rough ideas from the user.

## Working Principles

- Stay close to the user's material. Do not invent requirements, hardware, or systems that were not provided.
- Keep recommendations realistic for the current environment and resources.
- Prefer simple first-pass structures that can be refined later.
- Separate facts, assumptions, and suggestions clearly.
- When information is missing, state the gap briefly instead of filling it with speculation.

## Expected Output Style

- Keep writing concise and usable for reports, kickoff docs, architecture notes, and internal presentations.
- Avoid overexplaining. Focus on what the team needs to decide or build next.
- Use plain language unless a technical term is necessary.
- For diagrams, use clear layer-based structure:
  - Hardware / infrastructure
  - Agent or orchestration layer
  - Applications and workflows
  - Data and integrations
  - Logging, security, and governance

## Common Deliverables

- Project kickoff draft
- Architecture overview
- Use case shortlist
- Risks and considerations
- Implementation phases
- Meeting or workshop notes

## Agent and Framework Guidance

- Treat frameworks such as OpenClaw, Hermes agent, LangChain, LangGraph, and Google ADK as options to evaluate, not defaults.
- If a framework choice is not yet decided, present options with brief tradeoffs instead of making a hard recommendation.
- Custom agents are acceptable when the project needs tighter control, simpler integration, or better alignment with existing systems.

## Questions to Resolve Early

- What hardware is available?
- What applications already exist?
- Which workflows are highest priority?
- What data can AI access?
- What security or approval constraints apply?
- What does success look like for the first pilot?

## File and Content Conventions

- Keep new notes and drafts in markdown unless another format is requested.
- Use short headings and direct section labels.
- Reuse prior terminology from the project when possible.
- Do not rename the project or create unrelated branding language.

## Review Standard

- Check that the final output is consistent with the user's latest instructions.
- Check that the document can be reused across future AX Project tasks without needing major rewriting.
- Keep the tone professional, direct, and suitable for internal company use.
