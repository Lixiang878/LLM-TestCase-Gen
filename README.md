<div align="center">

# llm-testcase-gen

**LLM-powered unit-test case generator**

Parse Python functions → ask an LLM for cases → de-duplicate → report coverage.

[English](#english) · [中文](#中文)

</div>

---

<a id="english"></a>
## English

`llm-testcase-gen` turns a function's signature, parameters, docstring and
source into structured unit-test cases with the help of an LLM. It then
de-duplicates the cases and reports coverage across three dimensions:
**normal** (happy path), **boundary** (edge values), and **exception**
(invalid input).

> Built for the 2027 autumn-recruitment portfolio of 李想 (Lixiang). The
> *core* runs on the Python standard library alone — no network, no heavy
> dependencies — so it installs in seconds and is fully testable offline.

### Features

- **Zero hard dependencies** for the core (`ast`, `json`, `hashlib`, ...).
  Network-backed providers (`openai`) import lazily.
- **AST parser** extracts functions, parameters (with annotations & defaults),
  docstrings and return types — no regex hacks.
- **Pluggable providers**: a deterministic offline `MockProvider` (great for
  CI and demos) and an `OpenAIProvider` for any OpenAI-compatible endpoint
  (OpenAI, Wenxin, Qwen, local vLLM, ...).
- **Strategy-driven prompts**: `normal` / `boundary` / `exception` passes.
- **Robust JSON extraction** from LLM replies (tolerates code fences & prose).
- **De-duplication** by canonical input key (order-independent).
- **Coverage report** with a simple function×dimension score.

### Install

```bash
pip install -e .
# or, for development with tests:
pip install -e ".[dev]"
```

### Quick start (offline, no API key)

```bash
# End-to-end demo on the bundled sample module:
llm-testcase-gen demo

# Generate cases for one file:
llm-testcase-gen gen -f examples/sample_math.py --provider mock --dedup -o cases.json

# Inspect coverage:
llm-testcase-gen report cases.json

# De-duplicate an existing JSON:
llm-testcase-gen dedupe cases.json -o cases.dedup.json
```

### With a real LLM

```bash
export OPENAI_API_KEY=sk-...
llm-testcase-gen gen -f my_module.py --provider openai \
    --model gpt-4o-mini --strategies normal,boundary,exception -o cases.json
```

For Wenxin / Qwen / a local server, set `--base-url`:

```bash
llm-testcase-gen gen -f my_module.py --provider openai \
    --base-url https://my-endpoint/v1 --model qwen-max -o cases.json
```

### Output schema

Each case is a JSON object:

```json
{
  "id": "a1b2c3d4e5f6",
  "target": "divide",
  "kind": "exception",
  "description": "Division by zero raises.",
  "inputs": {"a": 1.0, "b": 0.0},
  "expected": "Raises ZeroDivisionError.",
  "assertions": ["with pytest.raises(ZeroDivisionError): divide(1.0, 0.0)"],
  "provider": "mock"
}
```

### Project layout

```
llm-testcase-gen/
├── README.md
├── pyproject.toml
├── requirements.txt
├── src/llm_testcase_gen/
│   ├── models.py          # FunctionSpec / ParamInfo / TestCase
│   ├── parser.py          # AST-based extraction
│   ├── provider.py        # MockProvider / OpenAIProvider
│   ├── prompt_builder.py  # strategy prompts
│   ├── generator.py       # orchestration + JSON parsing
│   ├── dedupe.py          # de-duplication
│   ├── coverage.py        # coverage report
│   └── cli.py             # command-line entry
├── tests/                 # offline pytest suite
├── examples/              # sample module + generated cases
├── configs/               # default generation config
└── .github/               # CI + issue/PR templates
```

### Tests

```bash
pytest -q
```

---

<a id="中文"></a>
## 中文

`llm-testcase-gen` 借助大语言模型，将函数的签名、参数、文档字符串与源码转化为
结构化的单元测试用例，随后自动去重，并从三个维度统计覆盖率：**正常路径
（normal）**、**边界条件（boundary）**、**异常输入（exception）**。

> 本项目为李想 2027 秋招作品集的一部分。**核心逻辑零第三方依赖**（仅用 Python
> 标准库），安装迅速、可完全离线测试。

### 特性

- **核心零硬依赖**：仅依赖 `ast`、`json`、`hashlib` 等标准库；联网的
  `openai` 提供者按需懒加载。
- **AST 解析**：提取函数、参数（含类型注解与默认值）、文档字符串与返回类型。
- **可插拔提供者**：确定性的离线 `MockProvider`（适合 CI 与演示），以及兼容
  OpenAI 接口的 `OpenAIProvider`（OpenAI / 文心 / 通义 / 本地 vLLM 等）。
- **策略化提示**：`normal` / `boundary` / `exception` 三遍生成。
- **鲁棒 JSON 解析**：兼容代码围栏与冗余文本。
- **去重**：基于规范化输入指纹（与参数顺序无关）。
- **覆盖率报告**：函数 × 维度 的简单得分。

### 安装

```bash
pip install -e .
pip install -e ".[dev]"   # 含测试依赖
```

### 快速开始（离线，无需 API Key）

```bash
llm-testcase-gen demo
llm-testcase-gen gen -f examples/sample_math.py --provider mock --dedup -o cases.json
llm-testcase-gen report cases.json
```

### 使用真实大模型

```bash
export OPENAI_API_KEY=sk-...
llm-testcase-gen gen -f my_module.py --provider openai --model gpt-4o-mini -o cases.json
```

第三方兼容端点（文心 / 通义 / 本地服务）通过 `--base-url` 指定：

```bash
llm-testcase-gen gen -f my_module.py --provider openai \
    --base-url https://my-endpoint/v1 --model qwen-max -o cases.json
```

### 许可证

MIT © 2026 李想 (Lixiang)

---

<div align="center">

**Star ⭐ if this helps your workflow. Issues and PRs welcome.**

</div>
