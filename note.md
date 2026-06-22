#Agents
##Concepts and Components

### Isolated Subagents for Parallel Workstreams
- main agent assigns subgents tasks
- parallel execution
- isolation benefits: a agent's crash doen't pollute the memory or crash the other agent or parent agent.

### Python Scripts via RPC (Remote Prodedure Calls)
Python Scripts via RPC (Remote Procedure Calls)Instead of forcing the local LLM to constantly output multi-step structural text instructions (which is slow and expensive on local hardware), Hermes utilizes a Skill Factory to compile plans into standalone Python scripts.
(more : https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/code-execution.md)

- The Mechanism: The agent generates a local .py script containing all the logical steps of a pipeline. When this script runs, it interacts back with the agent's core system tools using RPC over an internal network socket.
- Code as the Orchestrator: Instead of the LLM deciding step-by-step what to do next over 10 consecutive model generations, the compiled code takes over the execution flow. The code calls tools natively, loops through file paths, handles errors, and aggregates data directly.
- Zero-Context-Cost turns : standard agent setup (LangChain) , every tool execution requires a "turn" that is sent to LLM as contexts (tokens). LLM decides to call as many tools as necessary that costs a lot of tokens and computations.
- Alternatively, hermes agent generates python script to call required tools programatically. (1 turn, less tokens).

note : why not open source agent frameworks?
- they are so general. I don't need general expert. I need agents that have specific skills for the specific tasks and workflows.
- learn their features, the architecture and concepts especially how they handle security, memory, code scecution (programmatic tool calling)

### Batch Processing
Batch processing lets you run the Hermes agent across hundreds or thousands of prompts in parallel, generating structured trajectory data. This is primarily used for training data generation — producing ShareGPT-format trajectories with tool usage statistics that can be used for fine-tuning or evaluation.

### [Learn] Agent SDK and Frameworks
- Claude Agent SDK [https://code.claude.com/docs/en/agent-sdk]
- Cline Kanban
- Paperclipai/Paperclip
- NanoClaw Agent Swarms 
