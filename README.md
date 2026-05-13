# Korean Translation Middleware

Bidirectional Korean-English translation middleware for LLM APIs.

## Installation

```bash
pip install -e .
```

## Quick Start

### 1. Configure

Create `~/.ko-translate/config.toml`:

```toml
[engine]
engine = "local"
local_model_url = "http://127.0.0.1:1234"
local_model_name = "gemma-4-korean-uncensored"
```

### 2. Start Proxy

```bash
ko-proxy --host 127.0.0.1 --port 8080
```

### 3. Use with CLI

```bash
ko-translate "안녕하세요" --direction ko-en
```

### 4. Use as Library

```python
from ko_translate import Translator

translator = Translator.create()
result = await translator.translate("안녕하세요")
print(result.translated)
```

## Environment Variables

- `KO_TRANSLATE_ENGINE`: Translation engine (local, openai)
- `KO_TRANSLATE_LOCAL_MODEL_URL`: LM Studio URL
- `KO_TRANSLATE_FAIL_MODE`: open, closed, configurable
- `KO_TRANSLATE_LOG_LEVEL`: debug, info, warning, error