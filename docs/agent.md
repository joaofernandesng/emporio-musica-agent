# Agent configuration

Environment variables (see `.env.example`; copy it to `.env`, never commit it):

| Variable | Meaning |
|---|---|
| `OPENAI_API_KEY` | API key (required). |
| `OPENAI_MODEL` | Chat model id (required). |
| `OPENAI_BASE_URL` | Optional endpoint of an OpenAI-compatible provider; empty means the OpenAI default. |
| `EMPORIO_NOW` | Optional fixed "current time" (ISO 8601, Campo Grande); empty means the real clock. |
| `OPENAI_PRICE_INPUT_PER_1M`, `OPENAI_PRICE_OUTPUT_PER_1M` | Optional USD prices per 1M tokens; only used to estimate cost in `python -m emporio.evals` and `python -m emporio.demo` (otherwise only tokens are shown). |

## Compatibility

The only request fields are `model`, `messages` and `tools`. No `temperature`,
`max_tokens`, `reasoning_effort` or other vendor-specific parameter is sent, so
GPT-5-family models (which reject non-default sampling parameters) and other
OpenAI-compatible providers accept the call as is.
