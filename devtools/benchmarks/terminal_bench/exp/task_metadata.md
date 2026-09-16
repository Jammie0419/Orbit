# Terminal-Bench 2.1 任务元数据

> 从 `task.toml` 自动提取，共 89 个任务。

## 总览

| 难度 | 数量 | 占比 |
|------|------|------|
| Easy | 4 | 4.5% |
| Medium | 55 | 61.8% |
| Hard | 30 | 33.7% |

- **Agent 超时范围**: 10 分钟 ~ 3 小时 20 分钟
- **平均超时**: 28m27s
- **最常见超时**: 15 分钟（43 个任务）
- **GPU 需求**: 0 个任务（全部 CPU-only）
- **8GB 内存任务**: 7 个

---

## EASY 任务 (4 个)

### cobol-modernization

**描述**: Evaluates the ability to reverse-engineer and reimplement a COBOL program's business logic in Python with exact output reproduction.

| 属性 | 值 |
|------|------|
| 作者 | Akshay Anand |
| 难度 | easy |
| 类别 | software-engineering |
| 标签 | coding |
| 关键词 | coding, software-engineering |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 1 小时 10 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/cobol-modernization:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### fix-git

**描述**: Evaluates the ability to recover lost Git commits from a detached HEAD state and merge them back into the master branch.

| 属性 | 值 |
|------|------|
| 作者 | TheMikeMerrill |
| 难度 | easy |
| 类别 | software-engineering |
| 标签 | coding, version-control |
| 关键词 | coding, version-control, software-engineering |
| 专家估算时间 | 5 分钟 |
| 初级估算时间 | 20 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/fix-git:20260403` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### overfull-hbox

**描述**: Evaluates the ability to fix LaTeX overfull hbox warnings by replacing words with valid synonyms while satisfying compilation and constraint requirements.

| 属性 | 值 |
|------|------|
| 作者 | Sam Buchanan |
| 难度 | easy |
| 类别 | debugging |
| 标签 | latex, document-processing, combinatorial-optimization |
| 关键词 | latex, document-processing, combinatorial-optimization, debugging |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 12m30s |
| Verifier 超时 | 6 分钟 |
| Docker 镜像 | `alexgshaw/overfull-hbox:20260403` |
| 内存 | 4 GB |
| CPU | 2 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### prove-plus-comm

**描述**: Evaluates the ability to complete an incomplete Coq proof of addition commutativity using inductive reasoning and formal verification tactics.

| 属性 | 值 |
|------|------|
| 作者 | TheMikeMerrill |
| 难度 | easy |
| 类别 | software-engineering |
| 标签 | coding |
| 关键词 | coding, software-engineering |
| 专家估算时间 | 5 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/prove-plus-comm:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

---

## MEDIUM 任务 (55 个)

### adaptive-rejection-sampler

**描述**: Evaluates the ability to implement an adaptive rejection sampler in R with proper statistical algorithms, modular design, input validation, log-concavity checking, and formal testing.

| 属性 | 值 |
|------|------|
| 作者 | jvpoulos |
| 难度 | medium |
| 类别 | scientific-computing |
| 标签 | applied-statistics, adaptive-rejection-sampling, Bayesian-inference, simulation |
| 关键词 | applied-statistics, adaptive-rejection-sampling, Bayesian-inference, simulation, scientific-computing |
| 专家估算时间 | 3 小时 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/adaptive-rejection-sampler:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### break-filter-js-from-html

**描述**: Evaluates the agent's ability to bypass an HTML sanitization filter by crafting malicious HTML that triggers JavaScript execution after filtering.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | security |
| 标签 | security |
| 关键词 | security |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 20 分钟 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/break-filter-js-from-html:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### build-cython-ext

**描述**: Evaluates the ability to compile and install a Python package with Cython extensions from source while fixing NumPy 2.x compatibility issues.

| 属性 | 值 |
|------|------|
| 作者 | Zizhao Chen |
| 难度 | medium |
| 类别 | debugging |
| 标签 | coding, dependency, compilation |
| 关键词 | coding, dependency, compilation, debugging |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/build-cython-ext:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### build-pmars

**描述**: Evaluates the ability to build pMARS from Debian source packages with X11 support disabled, requiring Makefile modification and headless compilation.

| 属性 | 值 |
|------|------|
| 作者 | Jeong Shin |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | build-tools, compilation, debian, gaming, pmars, corewars |
| 关键词 | build-tools, compilation, debian, gaming, pmars, corewars, software-engineering |
| 专家估算时间 | 1 小时 30 分钟 |
| 初级估算时间 | 4 小时 30 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/build-pmars:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### build-pov-ray

**描述**: Evaluates the ability to locate, download, patch, and compile legacy POV-Ray 2.2 raytracer from 1990s source archives on a modern system.

| 属性 | 值 |
|------|------|
| 作者 | Jeong Shin |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | build-tools, compilation, graphics, ray-tracing, legacy-software, research |
| 关键词 | build-tools, compilation, graphics, ray-tracing, legacy-software, research, software-engineering |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 3 小时 20 分钟 |
| Verifier 超时 | 3 小时 20 分钟 |
| Docker 镜像 | `alexgshaw/build-pov-ray:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### caffe-cifar-10

**描述**: Evaluates the ability to install and configure BVLC Caffe 1.0.0, train a CNN on CIFAR-10 for exactly 500 iterations in CPU-only mode, and achieve specified accuracy thresholds.

| 属性 | 值 |
|------|------|
| 作者 | Robert Amanfu |
| 难度 | medium |
| 类别 | machine-learning |
| 标签 | cnn, caffe |
| 关键词 | cnn, caffe, machine-learning |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/caffe-cifar-10:20260403` |
| 内存 | 8 GB |
| CPU | 4 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### chess-best-move

**描述**: Evaluates the agent's ability to analyze a chess position from an image, use a chess engine to find the best move(s), and handle multiple valid solutions.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | games |
| 关键词 | games |
| 专家估算时间 | 45 分钟 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/chess-best-move:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### code-from-image

**描述**: Evaluates an agent's ability to extract code from an image using OCR or vision models, implement the pseudocode logic with cryptographic hashing, and produce the correct output.

| 属性 | 值 |
|------|------|
| 作者 | Guanghao Ye |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | ocr |
| 关键词 | ocr, software-engineering |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 20 分钟 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/code-from-image:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### compile-compcert

**描述**: Evaluates the ability to build the CompCert verified C compiler from source with proper configuration for the host architecture and dependencies.

| 属性 | 值 |
|------|------|
| 作者 | Robert Zhang |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | compilation, compilers |
| 关键词 | compilation, compilers, system-administration |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 40 分钟 |
| Verifier 超时 | 40 分钟 |
| Docker 镜像 | `alexgshaw/compile-compcert:20260403` |
| 内存 | 4 GB |
| CPU | 2 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### constraints-scheduling

**描述**: Find an optimal 1-hour meeting slot for three people with complex availability constraints by parsing ICS calendars and applying constraint satisfaction with tie-breaking preferences.

| 属性 | 值 |
|------|------|
| 作者 | Derek Pham |
| 难度 | medium |
| 类别 | personal-assistant |
| 标签 | calendar, scheduling, constraint-satisfaction, ics-parsing, temporal-reasoning |
| 关键词 | calendar, scheduling, constraint-satisfaction, ics-parsing, temporal-reasoning, personal-assistant |
| 专家估算时间 | 15 分钟 |
| 初级估算时间 | 30 分钟 |
| Agent 超时 | 20 分钟 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/constraints-scheduling:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### count-dataset-tokens

**描述**: Evaluates the ability to count tokens in a filtered HuggingFace dataset using a specific tokenizer.

| 属性 | 值 |
|------|------|
| 作者 | Ryan Marten |
| 难度 | medium |
| 类别 | model-training |
| 标签 | machine-learning, data, datasets, tokenization, huggingface |
| 关键词 | machine-learning, data, datasets, tokenization, huggingface, model-training |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/count-dataset-tokens:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### crack-7z-hash

**描述**: Evaluates the ability to crack a password-protected 7z archive using John the Ripper and extract secret contents.

| 属性 | 值 |
|------|------|
| 作者 | Jan-Lucas Uslu |
| 难度 | medium |
| 类别 | security |
| 标签 | decrypt, security, file-operations |
| 关键词 | decrypt, security, file-operations |
| 专家估算时间 | 5 分钟 |
| 初级估算时间 | 10 分钟 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/crack-7z-hash:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### custom-memory-heap-crash

**描述**: Evaluates the ability to debug and fix a C++ program that crashes in release mode due to a static initialization order issue with custom memory allocators and STL locale facets.

| 属性 | 值 |
|------|------|
| 作者 | Boxuan Li |
| 难度 | medium |
| 类别 | debugging |
| 标签 | cpp, memory-management, debugging |
| 关键词 | cpp, memory-management, debugging |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 20 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/custom-memory-heap-crash:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### db-wal-recovery

**描述**: Tests the ability to decrypt an XOR-encrypted SQLite WAL file and recover complete database contents including write-ahead log changes.

| 属性 | 值 |
|------|------|
| 作者 | Xiangning Lin |
| 难度 | medium |
| 类别 | file-operations |
| 标签 | database, encryption, recovery |
| 关键词 | database, encryption, recovery, file-operations |
| 专家估算时间 | 45 分钟 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/db-wal-recovery:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### distribution-search

**描述**: Tests the ability to find a probability distribution satisfying precise dual KL divergence constraints through numerical optimization.

| 属性 | 值 |
|------|------|
| 作者 | Xuandong Zhao |
| 难度 | medium |
| 类别 | machine-learning |
| 标签 | coding, statistics, machine-learning |
| 关键词 | coding, statistics, machine-learning |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/distribution-search:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### dna-insert

**描述**: Evaluates the ability to design PCR primers for site-directed mutagenesis by analyzing plasmid sequences and applying molecular biology constraints on primer length and melting temperature.

| 属性 | 值 |
|------|------|
| 作者 | Karl Krauth |
| 难度 | medium |
| 类别 | scientific-computing |
| 标签 | biology, cloning |
| 关键词 | biology, cloning, scientific-computing |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/dna-insert:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### extract-elf

**描述**: Evaluates ability to parse ELF binary format and extract memory values from executable sections using Node.js.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | file-operations |
| 关键词 | file-operations |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/extract-elf:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### filter-js-from-html

**描述**: Evaluates the agent's ability to create a robust XSS filter that removes JavaScript from HTML files while preserving legitimate HTML structure and content.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | security |
| 标签 | security |
| 关键词 | security |
| 专家估算时间 | 45 分钟 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/filter-js-from-html:20251031` |
| 内存 | 8 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### financial-document-processor

**描述**: Evaluates OCR, document classification, financial data extraction from mixed JPG/PDF documents, and CSV generation with totals.

| 属性 | 值 |
|------|------|
| 作者 | Dariush Wahdany |
| 难度 | medium |
| 类别 | data-processing |
| 标签 | ocr, image-processing, financial, file-operations |
| 关键词 | ocr, image-processing, financial, file-operations, data-processing |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 20 分钟 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/financial-document-processor:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### gcode-to-text

**描述**: Tests the agent's ability to extract and decode text from a 3D printer G-code file by parsing movement commands, rendering them visually, and performing OCR.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | file-operations |
| 标签 | file-operations |
| 关键词 | file-operations |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 5 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/gcode-to-text:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### git-leak-recovery

**描述**: Evaluates the ability to recover secrets from unreachable git objects and completely remove them from repository history while preserving legitimate commits.

| 属性 | 值 |
|------|------|
| 作者 | Yiwei Dai |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | git, security |
| 关键词 | git, security, software-engineering |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/git-leak-recovery:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### git-multibranch

**描述**: Evaluates the ability to set up a Git server with SSH authentication, implement post-receive hooks for automated multi-branch deployment, and configure Nginx to serve branch-specific content over HTTPS.

| 属性 | 值 |
|------|------|
| 作者 | Vedang |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | system, version-control, web |
| 关键词 | system, version-control, web, system-administration |
| 专家估算时间 | 3 小时 |
| 初级估算时间 | 6 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/git-multibranch:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### headless-terminal

**描述**: Implement a Python class that provides a headless terminal interface supporting interactive bash shells, modifier keys, startup file sourcing, and state persistence between commands.

| 属性 | 值 |
|------|------|
| 作者 | Alex Shaw |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | bash, terminal |
| 关键词 | bash, terminal, software-engineering |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/headless-terminal:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### hf-model-inference

**描述**: Evaluates the ability to download a Hugging Face transformer model, create a Flask API for sentiment analysis, and run the service in the background with proper error handling.

| 属性 | 值 |
|------|------|
| 作者 | Junhong Shen |
| 难度 | medium |
| 类别 | data-science |
| 标签 | api, coding, data-processing, data-science |
| 关键词 | api, coding, data-processing, data-science |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/hf-model-inference:20260430` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### kv-store-grpc

**描述**: Evaluates the ability to build and deploy a gRPC-based key-value store server with Protocol Buffers, including service definition, code generation, implementation, and background process management.

| 属性 | 值 |
|------|------|
| 作者 | Minghao Yan |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | coding, file-operations, system |
| 关键词 | coding, file-operations, system, software-engineering |
| 专家估算时间 | 15 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/kv-store-grpc:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### large-scale-text-editing

**描述**: Evaluates the ability to efficiently transform a 1-million-row CSV file using keystroke-efficient Vim macros with strict command restrictions.

| 属性 | 值 |
|------|------|
| 作者 | Robert Zhang |
| 难度 | medium |
| 类别 | file-operations |
| 标签 | text-editing, large-scale-text-manipulation, vim, vim-macros |
| 关键词 | text-editing, large-scale-text-manipulation, vim, vim-macros, file-operations |
| 专家估算时间 | 40 分钟 |
| 初级估算时间 | 1 小时 30 分钟 |
| Agent 超时 | 20 分钟 |
| Verifier 超时 | 20 分钟 |
| Docker 镜像 | `alexgshaw/large-scale-text-editing:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### largest-eigenval

**描述**: Evaluates the agent's ability to optimize eigenvalue computation by implementing a faster alternative to numpy's default algorithm while maintaining mathematical correctness.

| 属性 | 值 |
|------|------|
| 作者 | Zizhao Chen |
| 难度 | medium |
| 类别 | mathematics |
| 标签 | coding, optimization, constraint, numerical-approximation |
| 关键词 | coding, optimization, constraint, numerical-approximation, mathematics |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/largest-eigenval:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### log-summary-date-ranges

**描述**: Evaluates the ability to analyze date-stamped log files, calculate counts across multiple date ranges, and generate structured CSV output.

| 属性 | 值 |
|------|------|
| 作者 | Orfeas Menis Mastromichalakis |
| 难度 | medium |
| 类别 | data-processing |
| 标签 | log-analysis, report-generation, data-processing |
| 关键词 | log-analysis, report-generation, data-processing |
| 专家估算时间 | 1 小时 15 分钟 |
| 初级估算时间 | 2 小时 30 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/log-summary-date-ranges:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### mailman

**描述**: Evaluates the ability to configure a functional mailing list server by integrating postfix and mailman3 with proper join/leave/announce workflows.

| 属性 | 值 |
|------|------|
| 作者 | Zizhao Chen |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | email-server, mailing-list |
| 关键词 | email-server, mailing-list, system-administration |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/mailman:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### merge-diff-arc-agi-task

**描述**: Evaluates git bundle merging, conflict resolution, and ARC-AGI style pattern recognition by requiring agents to fetch two git bundles, merge branches, and implement a generalizable transformation function from input/output examples.

| 属性 | 值 |
|------|------|
| 作者 | Zhi Wang |
| 难度 | medium |
| 类别 | debugging |
| 标签 | git, coding |
| 关键词 | git, coding, debugging |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 40 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/merge-diff-arc-agi-task:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### modernize-scientific-stack

**描述**: Evaluates the ability to migrate legacy Python 2.7 scientific computing code to modern Python 3 with proper dependencies and data processing.

| 属性 | 值 |
|------|------|
| 作者 | Jianbo Wu |
| 难度 | medium |
| 类别 | scientific-computing |
| 标签 | python-migration, scientific-computing, legacy-modernization, climate-science, data-processing |
| 关键词 | python-migration, scientific-computing, legacy-modernization, climate-science, data-processing |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 10 分钟 |
| Verifier 超时 | 10 分钟 |
| Docker 镜像 | `alexgshaw/modernize-scientific-stack:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### mteb-leaderboard

**描述**: Evaluates the ability to research and identify the best-performing embedding model on the Scandinavian MTEB leaderboard using data science tools and techniques.

| 属性 | 值 |
|------|------|
| 作者 | Niklas Muennighoff |
| 难度 | medium |
| 类别 | data-science |
| 标签 | retrieval, mteb |
| 关键词 | retrieval, mteb, data-science |
| 专家估算时间 | 5 分钟 |
| 初级估算时间 | 10 分钟 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/mteb-leaderboard:20260430` |
| 内存 | 8 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### mteb-retrieve

**描述**: Evaluates the agent's ability to perform semantic text retrieval using MTEB embeddings, computing cosine similarities and correctly ranking documents to find the 5th most similar match to a query.

| 属性 | 值 |
|------|------|
| 作者 | Niklas Muennighoff |
| 难度 | medium |
| 类别 | data-science |
| 标签 | data-processing, data-science, mteb |
| 关键词 | data-processing, data-science, mteb |
| 专家估算时间 | 15 分钟 |
| 初级估算时间 | 45 分钟 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/mteb-retrieve:20260430` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### multi-source-data-merger

**描述**: Evaluates an agent's ability to merge multi-format data sources (JSON, CSV, Parquet) with inconsistent schemas, applying field mappings and priority-based conflict resolution to produce standardized outputs.

| 属性 | 值 |
|------|------|
| 作者 | Xin Lan |
| 难度 | medium |
| 类别 | data-processing |
| 标签 | data-processing, etl, schema-mapping, conflict-resolution, pandas, parquet |
| 关键词 | data-processing, etl, schema-mapping, conflict-resolution, pandas, parquet |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/multi-source-data-merger:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### nginx-request-logging

**描述**: Evaluates the ability to install and configure Nginx with advanced request logging, rate limiting, and custom error pages.

| 属性 | 值 |
|------|------|
| 作者 | Junhong Shen |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | web-server |
| 关键词 | web-server, system-administration |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/nginx-request-logging:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### openssl-selfsigned-cert

**描述**: Evaluates an agent's ability to generate self-signed TLS certificates using OpenSSL, manage cryptographic keys with proper permissions, and create verification scripts.

| 属性 | 值 |
|------|------|
| 作者 | Junhong Shen |
| 难度 | medium |
| 类别 | security |
| 标签 | coding, file-operations, security, system |
| 关键词 | coding, file-operations, security, system |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/openssl-selfsigned-cert:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### polyglot-c-py

**描述**: Create a single polyglot source file that computes Fibonacci numbers when executed as both Python 3 and C code.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | coding |
| 关键词 | coding, software-engineering |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/polyglot-c-py:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### portfolio-optimization

**描述**: Evaluates the ability to implement a high-performance C extension for Python that performs portfolio risk and return calculations at least 1.2x faster than a pure Python baseline while maintaining numerical accuracy.

| 属性 | 值 |
|------|------|
| 作者 | Yanhao Li |
| 难度 | medium |
| 类别 | optimization |
| 标签 | c-programming, python-extension, optimization |
| 关键词 | c-programming, python-extension, optimization |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/portfolio-optimization:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### pypi-server

**描述**: Evaluates the ability to create a Python package, build it, set up a local PyPI server, and make the package installable from the server.

| 属性 | 值 |
|------|------|
| 作者 | Anurag Kashyap |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | coding, system |
| 关键词 | coding, system, software-engineering |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/pypi-server:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### pytorch-model-cli

**描述**: Evaluates the ability to convert PyTorch model weights to JSON, implement neural network inference in C, and create a command-line tool for MNIST digit prediction.

| 属性 | 值 |
|------|------|
| 作者 | Jan-Lucas Uslu |
| 难度 | medium |
| 类别 | model-training |
| 标签 | coding, C, pytorch |
| 关键词 | coding, C, pytorch, model-training |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/pytorch-model-cli:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### pytorch-model-recovery

**描述**: Evaluates the ability to reverse-engineer a PyTorch Transformer model architecture from a state dictionary, load pre-trained weights, and selectively fine-tune specific layers to improve performance on a dataset.

| 属性 | 值 |
|------|------|
| 作者 | Akshay Anand |
| 难度 | medium |
| 类别 | model-training |
| 标签 | coding, pytorch, machine-learning |
| 关键词 | coding, pytorch, machine-learning, model-training |
| 专家估算时间 | 15 分钟 |
| 初级估算时间 | 1 小时 10 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/pytorch-model-recovery:20260430` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### qemu-alpine-ssh

**描述**: Evaluates the ability to start an Alpine Linux VM in QEMU and configure SSH server access with proper networking and authentication.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | sys-admin |
| 关键词 | sys-admin, system-administration |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/qemu-alpine-ssh:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### qemu-startup

**描述**: Evaluates the agent's ability to configure and start a QEMU virtual machine with telnet-accessible serial console, requiring knowledge of QEMU command-line options, network configuration, and system readiness verification.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | sys-admin |
| 关键词 | sys-admin, system-administration |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/qemu-startup:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### query-optimize

**描述**: Evaluates the ability to optimize a slow SQL query with correlated subqueries by rewriting it using CTEs and window functions while preserving exact output.

| 属性 | 值 |
|------|------|
| 作者 | Shreyas Pimpalgaonkar |
| 难度 | medium |
| 类别 | data-science |
| 标签 | query-optimization, sql-query |
| 关键词 | query-optimization, sql-query, data-science |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/query-optimize:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### raman-fitting

**描述**: Evaluates the ability to fit Lorentzian curves to Raman spectroscopy data, extract peak parameters, and perform scientific data analysis using Python.

| 属性 | 值 |
|------|------|
| 作者 | Jan-Lucas Uslu |
| 难度 | medium |
| 类别 | scientific-computing |
| 标签 | coding, fitting, analysis, physics |
| 关键词 | coding, fitting, analysis, physics, scientific-computing |
| 专家估算时间 | 5 分钟 |
| 初级估算时间 | 30 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/raman-fitting:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### regex-log

**描述**: Tests the ability to construct a complex regular expression that matches dates in log lines containing valid IPv4 addresses while handling edge cases and boundary conditions.

| 属性 | 值 |
|------|------|
| 作者 | Orfeas Menis Mastromichalakis |
| 难度 | medium |
| 类别 | data-processing |
| 标签 | regex, string-parsing, log-analysis |
| 关键词 | regex, string-parsing, log-analysis, data-processing |
| 专家估算时间 | 45 分钟 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/regex-log:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### reshard-c4-data

**描述**: Evaluates the ability to create Python scripts for bidirectional data resharding with file size and directory constraints, using proper dependency management.

| 属性 | 值 |
|------|------|
| 作者 | jeffreywpli / dwahdany |
| 难度 | medium |
| 类别 | data-science |
| 标签 | coding, data-processing, file-operations |
| 关键词 | coding, data-processing, file-operations, data-science |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/reshard-c4-data:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### rstan-to-pystan

**描述**: Evaluates the ability to convert an RStan Gaussian Process script to functionally equivalent PyStan 3.10.0 code, including complex installation, hyperparameter mapping, and numerical verification of posterior estimates.

| 属性 | 值 |
|------|------|
| 作者 | Zhiwei Xu |
| 难度 | medium |
| 类别 | data-science |
| 标签 | pystan, rstan, gaussian-process |
| 关键词 | pystan, rstan, gaussian-process, data-science |
| 专家估算时间 | 3 小时 |
| 初级估算时间 | 48 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/rstan-to-pystan:20251031` |
| 内存 | 8 GB |
| CPU | 4 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### sanitize-git-repo

**描述**: Evaluates the ability to identify and sanitize sensitive API keys and tokens from a Git repository by replacing them with placeholders without modifying unrelated files.

| 属性 | 值 |
|------|------|
| 作者 | jeffreywpli |
| 难度 | medium |
| 类别 | security |
| 标签 | security, system, version-control |
| 关键词 | security, system, version-control |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/sanitize-git-repo:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### schemelike-metacircular-eval

**描述**: Evaluates the ability to implement a metacircular evaluator in Scheme that can interpret itself and a comprehensive suite of Scheme programs.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 5 小时 |
| 初级估算时间 | 40 小时 40 分钟 |
| Agent 超时 | 40 分钟 |
| Verifier 超时 | 40 分钟 |
| Docker 镜像 | `alexgshaw/schemelike-metacircular-eval:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### sqlite-db-truncate

**描述**: Evaluates the ability to recover data from a corrupted SQLite database using binary file analysis and data recovery techniques.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | medium |
| 类别 | debugging |
| 标签 | file-operations |
| 关键词 | file-operations, debugging |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/sqlite-db-truncate:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### sqlite-with-gcov

**描述**: Evaluates the ability to compile SQLite from source with gcov instrumentation and make it available in the system PATH.

| 属性 | 值 |
|------|------|
| 作者 | Mike Merrill |
| 难度 | medium |
| 类别 | system-administration |
| 标签 | software-installation, system |
| 关键词 | software-installation, system, system-administration |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/sqlite-with-gcov:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### tune-mjcf

**描述**: Evaluates the ability to optimize MuJoCo physics simulation parameters to achieve a 40% speedup while maintaining physical accuracy within specified tolerances.

| 属性 | 值 |
|------|------|
| 作者 | Zizhao Chen |
| 难度 | medium |
| 类别 | scientific-computing |
| 标签 | mujoco, physics, simulation, numerical-optimization |
| 关键词 | mujoco, physics, simulation, numerical-optimization, scientific-computing |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/tune-mjcf:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### vulnerable-secret

**描述**: Evaluates the agent's ability to analyze a binary executable, identify and exploit a buffer overflow vulnerability to bypass authentication, and extract a hidden secret flag.

| 属性 | 值 |
|------|------|
| 作者 | Justin Bauer |
| 难度 | medium |
| 类别 | security |
| 标签 | security, file-operations |
| 关键词 | security, file-operations |
| 专家估算时间 | 20 分钟 |
| 初级估算时间 | 2 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/vulnerable-secret:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### winning-avg-corewars

**描述**: Evaluates the ability to write a competitive CoreWars Redcode warrior that achieves specific win rates against five diverse opponent strategies.

| 属性 | 值 |
|------|------|
| 作者 | Jeong Shin |
| 难度 | medium |
| 类别 | software-engineering |
| 标签 | pmars, corewars, gaming |
| 关键词 | pmars, corewars, gaming, software-engineering |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/winning-avg-corewars:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

---

## HARD 任务 (30 个)

### bn-fit-modify

**描述**: Evaluates the ability to recover a Bayesian Network DAG structure from data, perform causal interventions, and sample from the modified network.

| 属性 | 值 |
|------|------|
| 作者 | Gabriel Dreiman |
| 难度 | hard |
| 类别 | scientific-computing |
| 标签 | bayesian-network, stats |
| 关键词 | bayesian-network, stats, scientific-computing |
| 专家估算时间 | 8 小时 |
| 初级估算时间 | 16 小时 40 分钟 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/bn-fit-modify:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### cancel-async-tasks

**描述**: Evaluates the ability to implement async task concurrency control with proper cleanup on cancellation, including the edge case of queued tasks.

| 属性 | 值 |
|------|------|
| 作者 | Alex Shaw |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | async, concurrency, python |
| 关键词 | async, concurrency, python, software-engineering |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 10 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/cancel-async-tasks:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### circuit-fibsqrt

**描述**: Evaluates the agent's ability to implement complex mathematical functions (Fibonacci of integer square root) using only combinational and sequential logic gates in a hardware description format.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 16 小时 |
| 初级估算时间 | 40 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/circuit-fibsqrt:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### configure-git-webserver

**描述**: Evaluates the ability to configure a Git server with automatic deployment to an nginx web server using post-receive hooks.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | system-administration |
| 标签 | system, version-control, web |
| 关键词 | system, version-control, web, system-administration |
| 专家估算时间 | 15 分钟 |
| 初级估算时间 | 1 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/configure-git-webserver:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### dna-assembly

**描述**: Evaluates the ability to design PCR primers for Golden Gate assembly by applying molecular biology knowledge and bioinformatics tools to meet complex cloning constraints.

| 属性 | 值 |
|------|------|
| 作者 | Karl Krauth |
| 难度 | hard |
| 类别 | scientific-computing |
| 标签 | biology, cloning |
| 关键词 | biology, cloning, scientific-computing |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 3 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/dna-assembly:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### extract-moves-from-video

**描述**: Evaluates the agent's ability to download a YouTube video, extract text commands through OCR or transcription, and produce a formatted text file with 90% accuracy.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | file-operations |
| 标签 | file-operations, web, video-processing |
| 关键词 | file-operations, web, video-processing |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 8 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/extract-moves-from-video:20260403` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### feal-differential-cryptanalysis

**描述**: Evaluates the ability to implement differential cryptanalysis on a FEAL-like cipher to recover a round key through chosen plaintext attacks.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | mathematics |
| 标签 | software-engineering |
| 关键词 | software-engineering, mathematics |
| 专家估算时间 | 8 小时 |
| 初级估算时间 | 320 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/feal-differential-cryptanalysis:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### feal-linear-cryptanalysis

**描述**: Evaluates the ability to perform linear cryptanalysis on a FEAL-like cipher to recover encryption keys from known plaintext-ciphertext pairs.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | mathematics |
| 标签 | software-engineering |
| 关键词 | software-engineering, mathematics |
| 专家估算时间 | 16 小时 |
| 初级估算时间 | 320 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/feal-linear-cryptanalysis:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### fix-code-vulnerability

**描述**: Evaluates the ability to identify and fix a CRLF injection vulnerability (CWE-93) in HTTP header handling code by adding input validation to reject control characters.

| 属性 | 值 |
|------|------|
| 作者 | Yue Liu |
| 难度 | hard |
| 类别 | security |
| 标签 | security, code-vulnerability, common-weakness-enumeration |
| 关键词 | security, code-vulnerability, common-weakness-enumeration |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 4 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/fix-code-vulnerability:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### fix-ocaml-gc

**描述**: Evaluates ability to debug and fix a runtime crash in the OCaml garbage collector's C implementation, requiring low-level debugging skills and understanding of compiler internals.

| 属性 | 值 |
|------|------|
| 作者 | Sadiq Jaffer |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | troubleshooting |
| 关键词 | troubleshooting, software-engineering |
| 专家估算时间 | 24 小时 |
| 初级估算时间 | 240 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/fix-ocaml-gc:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### gpt2-codegolf

**描述**: Evaluates the ability to implement a minimal, dependency-free C program that performs GPT-2 inference from TensorFlow checkpoints in under 5000 bytes.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 40 小时 |
| 初级估算时间 | 160 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/gpt2-codegolf:20251031` |
| 内存 | 8 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### install-windows-3.11

**描述**: Evaluates the ability to configure and run Windows 3.11 in QEMU with VNC display, web interface, and programmatic keyboard control for automated testing.

| 属性 | 值 |
|------|------|
| 作者 | Ivan Bercovich |
| 难度 | hard |
| 类别 | system-administration |
| 标签 | virtualization, qemu, windows-3.11, vnc, sys-admin, retro-computing |
| 关键词 | virtualization, qemu, windows-3.11, vnc, sys-admin, retro-computing, system-administration |
| 专家估算时间 | 5 小时 |
| 初级估算时间 | 10 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/install-windows-3.11:20251031` |
| 内存 | 4 GB |
| CPU | 2 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### llm-inference-batching-scheduler

**描述**: Implement a shape-aware batching scheduler for static-graph LLM inference that optimally packs requests into batches while meeting strict performance thresholds on cost, latency, and padding.

| 属性 | 值 |
|------|------|
| 作者 | Changran Hu |
| 难度 | hard |
| 类别 | machine-learning |
| 标签 | batching, inference, performance-optimization, scheduling |
| 关键词 | batching, inference, performance-optimization, scheduling, machine-learning |
| 专家估算时间 | 45 分钟 |
| 初级估算时间 | 7 小时 30 分钟 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/llm-inference-batching-scheduler:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### make-doom-for-mips

**描述**: Evaluates ability to cross-compile the DOOM game engine for MIPS architecture using LLVM toolchain and verify execution in a JavaScript emulator.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 8 小时 |
| 初级估算时间 | 32 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/make-doom-for-mips:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### make-mips-interpreter

**描述**: Implement a complete MIPS interpreter in JavaScript that can execute a DOOM ELF binary, handle system calls, and render the first game frame correctly.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 8 小时 |
| 初级估算时间 | 60 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/make-mips-interpreter:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### mcmc-sampling-stan

**描述**: Evaluates the ability to implement and run a hierarchical Bayesian model using R and Stan, including package installation, model specification with custom priors, MCMC sampling configuration, and posterior inference.

| 属性 | 值 |
|------|------|
| 作者 | Zhiwei Xu |
| 难度 | hard |
| 类别 | data-science |
| 标签 | R, stan, bayesian-statistics, mcmc |
| 关键词 | R, stan, bayesian-statistics, mcmc, data-science |
| 专家估算时间 | 3 小时 |
| 初级估算时间 | 48 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/mcmc-sampling-stan:20251031` |
| 内存 | 8 GB |
| CPU | 4 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### model-extraction-relu-logits

**描述**: Extracts hidden layer weights from a black-box ReLU neural network by querying outputs and identifying critical points where neurons activate.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | mathematics |
| 标签 | security |
| 关键词 | security, mathematics |
| 专家估算时间 | 8 小时 |
| 初级估算时间 | 40 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/model-extraction-relu-logits:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### password-recovery

**描述**: Evaluates an agent's ability to perform digital forensics by recovering a deleted password from fragmented data within a disk image using command-line tools.

| 属性 | 值 |
|------|------|
| 作者 | Harsh Raj |
| 难度 | hard |
| 类别 | security |
| 标签 | system, file-operations, troubleshooting |
| 关键词 | system, file-operations, troubleshooting, security |
| 专家估算时间 | 1 小时 40 分钟 |
| 初级估算时间 | 5 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/password-recovery:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### path-tracing

**描述**: Evaluates the ability to reverse-engineer and implement a path tracing renderer in C by analyzing a reference image and recreating it algorithmically.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | images |
| 关键词 | images, software-engineering |
| 专家估算时间 | 6 小时 |
| 初级估算时间 | 40 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/path-tracing:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### path-tracing-reverse

**描述**: Evaluates the ability to reverse-engineer a compiled path tracing renderer and recreate functionally identical C source code under size constraints.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | images |
| 关键词 | images, software-engineering |
| 专家估算时间 | 2 小时 |
| 初级估算时间 | 24 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/path-tracing-reverse:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### polyglot-rust-c

**描述**: Evaluates the ability to write a polyglot program that compiles and runs correctly as both Rust and C++ code, computing Fibonacci numbers.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | coding, no-verified-solution |
| 关键词 | coding, no-verified-solution, software-engineering |
| 专家估算时间 | 3 小时 |
| 初级估算时间 | 12 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/polyglot-rust-c:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### protein-assembly

**描述**: Evaluates the ability to design a fusion protein gBlock by querying bioinformatics APIs, selecting proteins based on spectral properties, and applying codon optimization with GC content constraints.

| 属性 | 值 |
|------|------|
| 作者 | Karl Krauth |
| 难度 | hard |
| 类别 | scientific-computing |
| 标签 | biology, cloning, proteins |
| 关键词 | biology, cloning, proteins, scientific-computing |
| 专家估算时间 | 1 小时 |
| 初级估算时间 | 5 小时 |
| Agent 超时 | 30 分钟 |
| Verifier 超时 | 30 分钟 |
| Docker 镜像 | `alexgshaw/protein-assembly:20260403` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### regex-chess

**描述**: Evaluates the ability to implement a complete chess move generator using only regular expression transformations on FEN notation.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | software-engineering |
| 关键词 | software-engineering |
| 专家估算时间 | 24 小时 |
| 初级估算时间 | 80 小时 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/regex-chess:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### sam-cell-seg

**描述**: Evaluates the ability to implement a histopathology image segmentation pipeline using MobileSAM to convert rectangular cell masks to precise polyline contours.

| 属性 | 值 |
|------|------|
| 作者 | Gabriel Dreiman |
| 难度 | hard |
| 类别 | data-science |
| 标签 | image-processing, machine-learning, histopathology |
| 关键词 | image-processing, machine-learning, histopathology, data-science |
| 专家估算时间 | 10 小时 |
| 初级估算时间 | 20 小时 |
| Agent 超时 | 2 小时 |
| Verifier 超时 | 2 小时 |
| Docker 镜像 | `alexgshaw/sam-cell-seg:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### sparql-university

**描述**: Evaluates the ability to write complex SPARQL queries with multiple constraints, aggregations, and date filtering against an RDF knowledge graph.

| 属性 | 值 |
|------|------|
| 作者 | Orfeas Menis Mastromichalakis |
| 难度 | hard |
| 类别 | data-querying |
| 标签 | knowledge-graph, sparql-query, information-retrieval |
| 关键词 | knowledge-graph, sparql-query, information-retrieval, data-querying |
| 专家估算时间 | 13 小时 20 分钟 |
| 初级估算时间 | 166 小时 40 分钟 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/sparql-university:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### torch-pipeline-parallelism

**描述**: Evaluates the ability to implement pipeline parallel training for LLaMA using PyTorch distributed primitives with all-forward-all-backward scheduling.

| 属性 | 值 |
|------|------|
| 作者 | Eric Wang |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | system |
| 关键词 | system, software-engineering |
| 专家估算时间 | 4 小时 |
| 初级估算时间 | 20 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/torch-pipeline-parallelism:20251031` |
| 内存 | 8 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### torch-tensor-parallelism

**描述**: Evaluates the ability to implement tensor parallelism for PyTorch linear layers with correct weight sharding, distributed forward/backward passes, and gradient computation across multiple processes.

| 属性 | 值 |
|------|------|
| 作者 | Eric Wang |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | system |
| 关键词 | system, software-engineering |
| 专家估算时间 | 4 小时 |
| 初级估算时间 | 20 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/torch-tensor-parallelism:20251031` |
| 内存 | 8 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### train-fasttext

**描述**: Train a FastText text classification model on Yelp review data that achieves >0.62 accuracy while staying under 150MB in size.

| 属性 | 值 |
|------|------|
| 作者 | jeffreywpli |
| 难度 | hard |
| 类别 | model-training |
| 标签 | data-processing, data-science |
| 关键词 | data-processing, data-science, model-training |
| 专家估算时间 | 30 分钟 |
| 初级估算时间 | 1 小时 30 分钟 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/train-fasttext:20251031` |
| 内存 | 4 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### video-processing

**描述**: Evaluates the ability to build a computer vision script that analyzes hurdle jump videos and extracts takeoff/landing frame numbers using OpenCV.

| 属性 | 值 |
|------|------|
| 作者 | Ivan Bercovich |
| 难度 | hard |
| 类别 | video-processing |
| 标签 | video-processing |
| 关键词 | video-processing |
| 专家估算时间 | 6 小时 40 分钟 |
| 初级估算时间 | 16 小时 40 分钟 |
| Agent 超时 | 1 小时 |
| Verifier 超时 | 1 小时 |
| Docker 镜像 | `alexgshaw/video-processing:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |

### write-compressor

**描述**: Evaluates the agent's ability to reverse-engineer a custom compression format and write a compatible compressor program.

| 属性 | 值 |
|------|------|
| 作者 | Nicholas Carlini |
| 难度 | hard |
| 类别 | software-engineering |
| 标签 | coding |
| 关键词 | coding, software-engineering |
| 专家估算时间 | 24 小时 |
| 初级估算时间 | 80 小时 |
| Agent 超时 | 15 分钟 |
| Verifier 超时 | 15 分钟 |
| Docker 镜像 | `alexgshaw/write-compressor:20251031` |
| 内存 | 2 GB |
| CPU | 1 |
| 存储 | 10 GB |
| 构建超时 | 10 分钟 |
| 网络访问 | 允许 |
