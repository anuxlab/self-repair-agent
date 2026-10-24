# self-repair-agent
The agent follows a generate → execute → diagnose → repair → re-execute loop. It uses LangChain because it provides a clean abstraction for the LLM, a tool-calling interface for running code, and easy memory of previous failures. DSPy could be used for prompt optimisation later, but LangChain is the most direct fit for a bug-fixing loop
