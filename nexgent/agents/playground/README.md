# OpenAI-compatible streaming chat

Create a `.env` file in this directory:

```bash
OPENAI_API_KEY=your-bearer-token
```

Then run the interactive client with Python’s standard library:

```bash
python3 chat.py
```

Shell environment variables take precedence over values in `.env`.

The defaults match the local endpoint and model from the example request:
`http://127.0.0.1:8000/v1/chat/completions` and `gemma-4-31b`.
`OPENAI_BASE_URL` may be either the full completions URL or a base URL such as
`http://127.0.0.1:8000/v1`.

Override them when needed:

```bash
python3 chat.py --url http://localhost:8000/v1/chat/completions --model gemma-4-31b
```
