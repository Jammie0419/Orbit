# Terminal-Bench 2.1 任务元数据

> 按**类别**分组，共 89 个任务。数据来源：`task.toml`。
> 
> 字段：Agent = 单任务 wall-clock 上限；Verifier = 验证器上限。所有任务的**构建超时统一为 10 分钟**（不再逐任务列出）。
> 
> pass@1 / pass@5 / Time 列：待填充。
> 
> 任务描述折叠在每个类别下方，展开可见。

---

## 总览

### 按类别

| 类别 | 数量 | 占比 |
|---|---|---|
| software-engineering | 26 | 29.2% |
| system-administration | 9 | 10.1% |
| data-science | 8 | 9.0% |
| scientific-computing | 8 | 9.0% |
| security | 8 | 9.0% |
| debugging | 5 | 5.6% |
| file-operations | 5 | 5.6% |
| data-processing | 4 | 4.5% |
| mathematics | 4 | 4.5% |
| model-training | 4 | 4.5% |
| machine-learning | 3 | 3.4% |
| data-querying | 1 | 1.1% |
| games | 1 | 1.1% |
| optimization | 1 | 1.1% |
| personal-assistant | 1 | 1.1% |
| video-processing | 1 | 1.1% |

### Agent 超时分布

| Agent 超时 | 数量 |
|---|---|
| 10 分钟 | 1 |
| 12m30s | 1 |
| 15 分钟 | 48 |
| 20 分钟 | 5 |
| 30 分钟 | 17 |
| 40 分钟 | 2 |
| 1 小时 | 13 |
| 2 小时 | 1 |
| 3 小时 20 分钟 | 1 |

### Verifier 超时分布

| Verifier 超时 | 数量 |
|---|---|
| 6 分钟 | 1 |
| 10 分钟 | 1 |
| 15 分钟 | 48 |
| 20 分钟 | 6 |
| 30 分钟 | 17 |
| 40 分钟 | 2 |
| 1 小时 | 12 |
| 2 小时 | 1 |
| 3 小时 20 分钟 | 1 |

### 内存分布

| 内存 | 数量 |
|---|---|
| 2 GB | 68 |
| 4 GB | 13 |
| 8 GB | 8 |

---

## software-engineering (26 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| cobol-modernization | easy | 15m | 15m | 2GB | 1 | 1.000 | 1.000 | exp/pass@1/cobol-modernization/2026-09-17__22-52-57 |
| fix-git | easy | 15m | 15m | 2GB | 1 | | | |
| prove-plus-comm | easy | 15m | 15m | 2GB | 1 | | | |
| build-pmars | medium | 15m | 15m | 2GB | 1 | | | |
| git-leak-recovery | medium | 15m | 15m | 2GB | 1 | | | |
| headless-terminal | medium | 15m | 15m | 2GB | 1 | | | |
| kv-store-grpc | medium | 15m | 15m | 2GB | 1 | | | |
| polyglot-c-py | medium | 15m | 15m | 2GB | 1 | | | |
| pypi-server | medium | 15m | 15m | 2GB | 1 | | | |
| code-from-image | medium | 20m | 20m | 2GB | 1 | | | |
| schemelike-metacircular-eval | medium | 40m | 40m | 2GB | 1 | | | |
| winning-avg-corewars | medium | 1h | 1h | 2GB | 1 | | | |
| build-pov-ray | medium | 3h20m | 3h20m | 2GB | 1 | | | |
| cancel-async-tasks | hard | 15m | 15m | 2GB | 1 | | | |
| gpt2-codegolf | hard | 15m | 15m | 8GB | 1 | | | |
| make-doom-for-mips | hard | 15m | 15m | 2GB | 1 | | | |
| polyglot-rust-c | hard | 15m | 15m | 2GB | 1 | | | |
| torch-pipeline-parallelism | hard | 15m | 15m | 8GB | 1 | | | |
| torch-tensor-parallelism | hard | 15m | 15m | 8GB | 1 | | | |
| write-compressor | hard | 15m | 15m | 2GB | 1 | | | |
| make-mips-interpreter | hard | 30m | 30m | 2GB | 1 | | | |
| path-tracing | hard | 30m | 30m | 2GB | 1 | | | |
| path-tracing-reverse | hard | 30m | 30m | 2GB | 1 | | | |
| circuit-fibsqrt | hard | 1h | 1h | 2GB | 1 | | | |
| fix-ocaml-gc | hard | 1h | 1h | 2GB | 1 | | | |
| regex-chess | hard | 1h | 1h | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (26)</summary>

- **cobol-modernization**: Evaluates the ability to reverse-engineer and reimplement a COBOL program's business logic in Python with exact output reproduction.
- **fix-git**: Evaluates the ability to recover lost Git commits from a detached HEAD state and merge them back into the master branch.
- **prove-plus-comm**: Evaluates the ability to complete an incomplete Coq proof of addition commutativity using inductive reasoning and formal verification tactics.
- **build-pmars**: Evaluates the ability to build pMARS from Debian source packages with X11 support disabled, requiring Makefile modification and headless compilation.
- **git-leak-recovery**: Evaluates the ability to recover secrets from unreachable git objects and completely remove them from repository history while preserving legitimate commits.
- **headless-terminal**: Implement a Python class that provides a headless terminal interface supporting interactive bash shells, modifier keys, startup file sourcing, and state persistence between commands.
- **kv-store-grpc**: Evaluates the ability to build and deploy a gRPC-based key-value store server with Protocol Buffers, including service definition, code generation, implementation, and background process management.
- **polyglot-c-py**: Create a single polyglot source file that computes Fibonacci numbers when executed as both Python 3 and C code.
- **pypi-server**: Evaluates the ability to create a Python package, build it, set up a local PyPI server, and make the package installable from the server.
- **code-from-image**: Evaluates an agent's ability to extract code from an image using OCR or vision models, implement the pseudocode logic with cryptographic hashing, and produce the correct output.
- **schemelike-metacircular-eval**: Evaluates the ability to implement a metacircular evaluator in Scheme that can interpret itself and a comprehensive suite of Scheme programs.
- **winning-avg-corewars**: Evaluates the ability to write a competitive CoreWars Redcode warrior that achieves specific win rates against five diverse opponent strategies.
- **build-pov-ray**: Evaluates the ability to locate, download, patch, and compile legacy POV-Ray 2.2 raytracer from 1990s source archives on a modern system.
- **cancel-async-tasks**: Evaluates the ability to implement async task concurrency control with proper cleanup on cancellation, including the edge case of queued tasks.
- **gpt2-codegolf**: Evaluates the ability to implement a minimal, dependency-free C program that performs GPT-2 inference from TensorFlow checkpoints in under 5000 bytes.
- **make-doom-for-mips**: Evaluates ability to cross-compile the DOOM game engine for MIPS architecture using LLVM toolchain and verify execution in a JavaScript emulator.
- **polyglot-rust-c**: Evaluates the ability to write a polyglot program that compiles and runs correctly as both Rust and C++ code, computing Fibonacci numbers.
- **torch-pipeline-parallelism**: Evaluates the ability to implement pipeline parallel training for LLaMA using PyTorch distributed primitives with all-forward-all-backward scheduling.
- **torch-tensor-parallelism**: Evaluates the ability to implement tensor parallelism for PyTorch linear layers with correct weight sharding, distributed forward/backward passes, and gradient computation across multiple processes.
- **write-compressor**: Evaluates the agent's ability to reverse-engineer a custom compression format and write a compatible compressor program.
- **make-mips-interpreter**: Implement a complete MIPS interpreter in JavaScript that can execute a DOOM ELF binary, handle system calls, and render the first game frame correctly.
- **path-tracing**: Evaluates the ability to reverse-engineer and implement a path tracing renderer in C by analyzing a reference image and recreating it algorithmically.
- **path-tracing-reverse**: Evaluates the ability to reverse-engineer a compiled path tracing renderer and recreate functionally identical C source code under size constraints.
- **circuit-fibsqrt**: Evaluates the agent's ability to implement complex mathematical functions (Fibonacci of integer square root) using only combinational and sequential logic gates in a hardware description format.
- **fix-ocaml-gc**: Evaluates ability to debug and fix a runtime crash in the OCaml garbage collector's C implementation, requiring low-level debugging skills and understanding of compiler internals.
- **regex-chess**: Evaluates the ability to implement a complete chess move generator using only regular expression transformations on FEN notation.

</details>

## system-administration (9 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| git-multibranch | medium | 15m | 15m | 2GB | 1 | | | |
| nginx-request-logging | medium | 15m | 15m | 2GB | 1 | | | |
| qemu-alpine-ssh | medium | 15m | 15m | 4GB | 1 | | | |
| qemu-startup | medium | 15m | 15m | 4GB | 1 | | | |
| sqlite-with-gcov | medium | 15m | 15m | 2GB | 1 | | | |
| mailman | medium | 30m | 30m | 2GB | 1 | | | |
| compile-compcert | medium | 40m | 40m | 4GB | 2 | | | |
| configure-git-webserver | hard | 15m | 15m | 2GB | 1 | | | |
| install-windows-3.11 | hard | 1h | 1h | 4GB | 2 | | | |

<details>
<summary><b>任务描述</b> (9)</summary>

- **git-multibranch**: Evaluates the ability to set up a Git server with SSH authentication, implement post-receive hooks for automated multi-branch deployment, and configure Nginx to serve branch-specific content over HTTPS.
- **nginx-request-logging**: Evaluates the ability to install and configure Nginx with advanced request logging, rate limiting, and custom error pages.
- **qemu-alpine-ssh**: Evaluates the ability to start an Alpine Linux VM in QEMU and configure SSH server access with proper networking and authentication.
- **qemu-startup**: Evaluates the agent's ability to configure and start a QEMU virtual machine with telnet-accessible serial console, requiring knowledge of QEMU command-line options, network configuration, and system readiness verification.
- **sqlite-with-gcov**: Evaluates the ability to compile SQLite from source with gcov instrumentation and make it available in the system PATH.
- **mailman**: Evaluates the ability to configure a functional mailing list server by integrating postfix and mailman3 with proper join/leave/announce workflows.
- **compile-compcert**: Evaluates the ability to build the CompCert verified C compiler from source with proper configuration for the host architecture and dependencies.
- **configure-git-webserver**: Evaluates the ability to configure a Git server with automatic deployment to an nginx web server using post-receive hooks.
- **install-windows-3.11**: Evaluates the ability to configure and run Windows 3.11 in QEMU with VNC display, web interface, and programmatic keyboard control for automated testing.

</details>

## data-science (8 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| hf-model-inference | medium | 15m | 15m | 2GB | 1 | | | |
| query-optimize | medium | 15m | 30m | 2GB | 1 | | | |
| mteb-retrieve | medium | 30m | 30m | 2GB | 1 | | | |
| rstan-to-pystan | medium | 30m | 30m | 8GB | 4 | | | |
| mteb-leaderboard | medium | 1h | 1h | 8GB | 1 | | | |
| reshard-c4-data | medium | 1h | 1h | 2GB | 1 | | | |
| mcmc-sampling-stan | hard | 30m | 30m | 8GB | 4 | | | |
| sam-cell-seg | hard | 2h | 2h | 4GB | 1 | | | |

<details>
<summary><b>任务描述</b> (8)</summary>

- **hf-model-inference**: Evaluates the ability to download a Hugging Face transformer model, create a Flask API for sentiment analysis, and run the service in the background with proper error handling.
- **query-optimize**: Evaluates the ability to optimize a slow SQL query with correlated subqueries by rewriting it using CTEs and window functions while preserving exact output.
- **mteb-retrieve**: Evaluates the agent's ability to perform semantic text retrieval using MTEB embeddings, computing cosine similarities and correctly ranking documents to find the 5th most similar match to a query.
- **rstan-to-pystan**: Evaluates the ability to convert an RStan Gaussian Process script to functionally equivalent PyStan 3.10.0 code, including complex installation, hyperparameter mapping, and numerical verification of posterior estimates.
- **mteb-leaderboard**: Evaluates the ability to research and identify the best-performing embedding model on the Scandinavian MTEB leaderboard using data science tools and techniques.
- **reshard-c4-data**: Evaluates the ability to create Python scripts for bidirectional data resharding with file size and directory constraints, using proper dependency management.
- **mcmc-sampling-stan**: Evaluates the ability to implement and run a hierarchical Bayesian model using R and Stan, including package installation, model specification with custom priors, MCMC sampling configuration, and posterior inference.
- **sam-cell-seg**: Evaluates the ability to implement a histopathology image segmentation pipeline using MobileSAM to convert rectangular cell masks to precise polyline contours.

</details>

## scientific-computing (8 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| modernize-scientific-stack | medium | 10m | 10m | 2GB | 1 | | | |
| adaptive-rejection-sampler | medium | 15m | 15m | 2GB | 1 | | | |
| raman-fitting | medium | 15m | 15m | 2GB | 1 | | | |
| tune-mjcf | medium | 15m | 15m | 2GB | 1 | | | |
| dna-insert | medium | 30m | 30m | 4GB | 1 | | | |
| dna-assembly | hard | 30m | 30m | 2GB | 1 | | | |
| protein-assembly | hard | 30m | 30m | 4GB | 1 | | | |
| bn-fit-modify | hard | 1h | 1h | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (8)</summary>

- **modernize-scientific-stack**: Evaluates the ability to migrate legacy Python 2.7 scientific computing code to modern Python 3 with proper dependencies and data processing.
- **adaptive-rejection-sampler**: Evaluates the ability to implement an adaptive rejection sampler in R with proper statistical algorithms, modular design, input validation, log-concavity checking, and formal testing.
- **raman-fitting**: Evaluates the ability to fit Lorentzian curves to Raman spectroscopy data, extract peak parameters, and perform scientific data analysis using Python.
- **tune-mjcf**: Evaluates the ability to optimize MuJoCo physics simulation parameters to achieve a 40% speedup while maintaining physical accuracy within specified tolerances.
- **dna-insert**: Evaluates the ability to design PCR primers for site-directed mutagenesis by analyzing plasmid sequences and applying molecular biology constraints on primer length and melting temperature.
- **dna-assembly**: Evaluates the ability to design PCR primers for Golden Gate assembly by applying molecular biology knowledge and bioinformatics tools to meet complex cloning constraints.
- **protein-assembly**: Evaluates the ability to design a fusion protein gBlock by querying bioinformatics APIs, selecting proteins based on spectral properties, and applying codon optimization with GC content constraints.
- **bn-fit-modify**: Evaluates the ability to recover a Bayesian Network DAG structure from data, perform causal interventions, and sample from the modified network.

</details>

## security (8 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| openssl-selfsigned-cert | medium | 15m | 15m | 2GB | 1 | | | |
| sanitize-git-repo | medium | 15m | 15m | 2GB | 1 | | | |
| vulnerable-secret | medium | 15m | 15m | 2GB | 1 | | | |
| break-filter-js-from-html | medium | 20m | 20m | 2GB | 1 | | | |
| crack-7z-hash | medium | 30m | 15m | 4GB | 1 | | | |
| filter-js-from-html | medium | 30m | 30m | 8GB | 1 | | | |
| fix-code-vulnerability | hard | 15m | 15m | 2GB | 1 | | | |
| password-recovery | hard | 15m | 15m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (8)</summary>

- **openssl-selfsigned-cert**: Evaluates an agent's ability to generate self-signed TLS certificates using OpenSSL, manage cryptographic keys with proper permissions, and create verification scripts.
- **sanitize-git-repo**: Evaluates the ability to identify and sanitize sensitive API keys and tokens from a Git repository by replacing them with placeholders without modifying unrelated files.
- **vulnerable-secret**: Evaluates the agent's ability to analyze a binary executable, identify and exploit a buffer overflow vulnerability to bypass authentication, and extract a hidden secret flag.
- **break-filter-js-from-html**: Evaluates the agent's ability to bypass an HTML sanitization filter by crafting malicious HTML that triggers JavaScript execution after filtering.
- **crack-7z-hash**: Evaluates the ability to crack a password-protected 7z archive using John the Ripper and extract secret contents.
- **filter-js-from-html**: Evaluates the agent's ability to create a robust XSS filter that removes JavaScript from HTML files while preserving legitimate HTML structure and content.
- **fix-code-vulnerability**: Evaluates the ability to identify and fix a CRLF injection vulnerability (CWE-93) in HTTP header handling code by adding input validation to reject control characters.
- **password-recovery**: Evaluates an agent's ability to perform digital forensics by recovering a deleted password from fragmented data within a disk image using command-line tools.

</details>

## debugging (5 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| overfull-hbox | easy | 12m30s | 6m | 4GB | 2 | | | |
| build-cython-ext | medium | 15m | 15m | 2GB | 1 | | | |
| merge-diff-arc-agi-task | medium | 15m | 15m | 4GB | 1 | | | |
| sqlite-db-truncate | medium | 15m | 15m | 2GB | 1 | | | |
| custom-memory-heap-crash | medium | 30m | 30m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (5)</summary>

- **overfull-hbox**: Evaluates the ability to fix LaTeX overfull hbox warnings by replacing words with valid synonyms while satisfying compilation and constraint requirements.
- **build-cython-ext**: Evaluates the ability to compile and install a Python package with Cython extensions from source while fixing NumPy 2.x compatibility issues.
- **merge-diff-arc-agi-task**: Evaluates git bundle merging, conflict resolution, and ARC-AGI style pattern recognition by requiring agents to fetch two git bundles, merge branches, and implement a generalizable transformation function from input/output examples.
- **sqlite-db-truncate**: Evaluates the ability to recover data from a corrupted SQLite database using binary file analysis and data recovery techniques.
- **custom-memory-heap-crash**: Evaluates the ability to debug and fix a C++ program that crashes in release mode due to a static initialization order issue with custom memory allocators and STL locale facets.

</details>

## file-operations (5 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| db-wal-recovery | medium | 15m | 15m | 2GB | 1 | | | |
| extract-elf | medium | 15m | 15m | 2GB | 1 | | | |
| gcode-to-text | medium | 15m | 15m | 2GB | 1 | | | |
| large-scale-text-editing | medium | 20m | 20m | 2GB | 1 | | | |
| extract-moves-from-video | hard | 30m | 30m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (5)</summary>

- **db-wal-recovery**: Tests the ability to decrypt an XOR-encrypted SQLite WAL file and recover complete database contents including write-ahead log changes.
- **extract-elf**: Evaluates ability to parse ELF binary format and extract memory values from executable sections using Node.js.
- **gcode-to-text**: Tests the agent's ability to extract and decode text from a 3D printer G-code file by parsing movement commands, rendering them visually, and performing OCR.
- **large-scale-text-editing**: Evaluates the ability to efficiently transform a 1-million-row CSV file using keystroke-efficient Vim macros with strict command restrictions.
- **extract-moves-from-video**: Evaluates the agent's ability to download a YouTube video, extract text commands through OCR or transcription, and produce a formatted text file with 90% accuracy.

</details>

## data-processing (4 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| log-summary-date-ranges | medium | 15m | 15m | 2GB | 1 | 1.000 | 1.000 | exp/pass@1/log-summary-date-ranges/2026-09-17__21-41-40 |
| multi-source-data-merger | medium | 15m | 15m | 2GB | 1 | 1.000 | 1.000 | exp/pass@1/multi-source-data-merger/2026-09-17__22-27-44 |
| regex-log | medium | 15m | 15m | 2GB | 1 | 1.000 | 1.000 | exp/pass@1/regex-log/2026-09-17__10-40-11 |
| financial-document-processor | medium | 20m | 20m | 4GB | 1 | 1.000 | 1.000 | exp/pass@1/financial-document-processor/2026-09-17__18-41-46 |

<details>
<summary><b>任务描述</b> (4)</summary>

- **log-summary-date-ranges**: Evaluates the ability to analyze date-stamped log files, calculate counts across multiple date ranges, and generate structured CSV output.
- **multi-source-data-merger**: Evaluates an agent's ability to merge multi-format data sources (JSON, CSV, Parquet) with inconsistent schemas, applying field mappings and priority-based conflict resolution to produce standardized outputs.
- **regex-log**: Tests the ability to construct a complex regular expression that matches dates in log lines containing valid IPv4 addresses while handling edge cases and boundary conditions.
- **financial-document-processor**: Evaluates OCR, document classification, financial data extraction from mixed JPG/PDF documents, and CSV generation with totals.

</details>

## mathematics (4 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| largest-eigenval | medium | 15m | 15m | 2GB | 1 | | | |
| model-extraction-relu-logits | hard | 15m | 15m | 2GB | 1 | | | |
| feal-differential-cryptanalysis | hard | 30m | 30m | 2GB | 1 | | | |
| feal-linear-cryptanalysis | hard | 30m | 30m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (4)</summary>

- **largest-eigenval**: Evaluates the agent's ability to optimize eigenvalue computation by implementing a faster alternative to numpy's default algorithm while maintaining mathematical correctness.
- **model-extraction-relu-logits**: Extracts hidden layer weights from a black-box ReLU neural network by querying outputs and identifying critical points where neurons activate.
- **feal-differential-cryptanalysis**: Evaluates the ability to implement differential cryptanalysis on a FEAL-like cipher to recover a round key through chosen plaintext attacks.
- **feal-linear-cryptanalysis**: Evaluates the ability to perform linear cryptanalysis on a FEAL-like cipher to recover encryption keys from known plaintext-ciphertext pairs.

</details>

## model-training (4 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| count-dataset-tokens | medium | 15m | 15m | 2GB | 1 | | | |
| pytorch-model-cli | medium | 15m | 15m | 2GB | 1 | | | |
| pytorch-model-recovery | medium | 15m | 15m | 2GB | 1 | | | |
| train-fasttext | hard | 1h | 1h | 4GB | 1 | | | |

<details>
<summary><b>任务描述</b> (4)</summary>

- **count-dataset-tokens**: Evaluates the ability to count tokens in a filtered HuggingFace dataset using a specific tokenizer.
- **pytorch-model-cli**: Evaluates the ability to convert PyTorch model weights to JSON, implement neural network inference in C, and create a command-line tool for MNIST digit prediction.
- **pytorch-model-recovery**: Evaluates the ability to reverse-engineer a PyTorch Transformer model architecture from a state dictionary, load pre-trained weights, and selectively fine-tune specific layers to improve performance on a dataset.
- **train-fasttext**: Train a FastText text classification model on Yelp review data that achieves >0.62 accuracy while staying under 150MB in size.

</details>

## machine-learning (3 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| caffe-cifar-10 | medium | 1h | 20m | 8GB | 4 | | | |
| distribution-search | medium | 1h | 1h | 2GB | 1 | | | |
| llm-inference-batching-scheduler | hard | 30m | 30m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (3)</summary>

- **caffe-cifar-10**: Evaluates the ability to install and configure BVLC Caffe 1.0.0, train a CNN on CIFAR-10 for exactly 500 iterations in CPU-only mode, and achieve specified accuracy thresholds.
- **distribution-search**: Tests the ability to find a probability distribution satisfying precise dual KL divergence constraints through numerical optimization.
- **llm-inference-batching-scheduler**: Implement a shape-aware batching scheduler for static-graph LLM inference that optimally packs requests into batches while meeting strict performance thresholds on cost, latency, and padding.

</details>

## data-querying (1 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| sparql-university | hard | 15m | 15m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (1)</summary>

- **sparql-university**: Evaluates the ability to write complex SPARQL queries with multiple constraints, aggregations, and date filtering against an RDF knowledge graph.

</details>

## games (1 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| chess-best-move | medium | 15m | 15m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (1)</summary>

- **chess-best-move**: Evaluates the agent's ability to analyze a chess position from an image, use a chess engine to find the best move(s), and handle multiple valid solutions.

</details>

## optimization (1 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| portfolio-optimization | medium | 1h | 1h | 4GB | 1 | | | |

<details>
<summary><b>任务描述</b> (1)</summary>

- **portfolio-optimization**: Evaluates the ability to implement a high-performance C extension for Python that performs portfolio risk and return calculations at least 1.2x faster than a pure Python baseline while maintaining numerical accuracy.

</details>

## personal-assistant (1 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| constraints-scheduling | medium | 20m | 20m | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (1)</summary>

- **constraints-scheduling**: Find an optimal 1-hour meeting slot for three people with complex availability constraints by parsing ICS calendars and applying constraint satisfaction with tie-breaking preferences.

</details>

## video-processing (1 个)

| 任务 | 难度 | Agent | Verifier | 内存 | CPU | pass@1 | pass@5 | Time |
|---|---|---|---|---|---|---|---|---|
| video-processing | hard | 1h | 1h | 2GB | 1 | | | |

<details>
<summary><b>任务描述</b> (1)</summary>

- **video-processing**: Evaluates the ability to build a computer vision script that analyzes hurdle jump videos and extracts takeoff/landing frame numbers using OpenCV.

</details>
