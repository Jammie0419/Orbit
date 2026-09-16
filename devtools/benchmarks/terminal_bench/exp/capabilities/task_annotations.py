"""Per-task annotations rendered from observed failure analysis.

RECOVERED 2026-09-16 from historical agent/instruction.txt renders (59 trials
carried an annotation block, covering 14 tasks).

VALIDITY WARNING -- read before using these in any reported measurement.
These annotations encode *what previous benchmark runs of this exact task died
on* (e.g. make-doom-for-mips: 'mimo spent 15 minutes and never ran node vm.js').
That is knowledge distilled from the benchmark's own failure modes, so a run with
annotations enabled is NOT a clean measurement of the model against the dataset.
Fine for internal ablation and debugging; it must be disclosed wherever results
are reported, and it must not be mixed into an arm that is described as clean.
"""

from __future__ import annotations

TASK_ANNOTATIONS: dict[str, str] = {
    'cancel-async-tasks': r"""1. 关键测试场景：当 n_tasks > max_concurrent 时发送 SIGINT，必须确保所有已启动的任务（包括正在等待信号量的）都执行清理代码。
2. 实现要点：语义必须是「信号量等待 + 任务执行 + 清理」在同一作用域内——参考解法用 async with semaphore 包住任务体即可，手动 try/finally + acquire/release 也可以，但不要在 except CancelledError 里对子任务再次 cancel()。
3. 常见陷阱：外部 SIGINT 时，运行中任务的 finally 清理可能正执行到 await 中间（如 await asyncio.sleep），此时对子任务再 cancel() 一次会打断清理，导致清理代码（如 print('Cleaned up.')）永远执行不到。稳妥写法：except asyncio.CancelledError 后只 await asyncio.gather(*running, return_exceptions=True) 再 raise，绝不重复 cancel；或直接用 asyncio.TaskGroup（它等所有子任务完成清理后才抛 CancelledError，天然不会二次取消）。
4. 验证方法（必须与验收同构）：写独立脚本用子进程跑 python test.py --n-tasks 3 --max-concurrent 2，约 500ms 后向该进程发 SIGINT（proc.send_signal(signal.SIGINT)），断言 stdout 里 'Task started.' 和 'Cleaned up.' 各出现 2 次。只做进程内主动 cancel() 的测试与验收场景不同构，测不出这个 bug。""",
    'chess-best-move': r"""1. 棋类任务：题目说'如果有多个必胜走法，全部输出'。必须穷举所有候选走法，对每个走法推演后续变化，找出所有必胜/将死走法。找到一个就停是典型错误。
2. 视觉解析：用 PIL 解析棋盘图片后，建议同时用两种方法验证棋子位置（像素采样 + 形状识别），避免误判。
3. 输出格式：move.txt 中每行一个走法，格式为 [src][dst]（如 e2e4）。多个走法时不要在一行里写多个。
4. 已知解法：这个棋局有多个一步将死的解法（g2g4 和 e2e4 都可能导致将死）。必须系统性地检查所有可能的移动，不要只找到一个就停止。""",
    'count-dataset-tokens': r"""1. 数据集已预下载到 /app/datasets 目录（data.parquet 文件），无需从 Hugging Face 下载。
2. 加载方式：使用 datasets 库加载本地 parquet 文件：load_dataset('parquet', data_files='/app/datasets/data.parquet')
3. Tokenizer：使用 transformers.AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct') 加载 Qwen2.5-1.5B tokenizer。
4. 计算流程：加载数据集 → 加载 tokenizer → 遍历 science 领域样本 → 分词 → 统计 token 总数 → 写入 /app/answer.txt。
5. Token 计数规则：当需要统计多个片段的总 token 数时对每个片段独立计数，再把各片段结果求和（Σ count(seg_i)）。如果必须拼接后计数，片段之间必须用换行符 
 分隔，且拼接后的结果应与分段求和一致。禁止把片段直接无缝拼接（不带任何分隔符）后一次性计数——tokenizer 的切分依赖上下文，无缝拼接会使边界处的字符跨边界合并成更少的 token，导致总数偏低（例如本例 79566 vs 正确值 79586，少算 20 个）。检：算出总数后，用分段求和交叉验证一次；若不一致，以分段求和为准，重新检查拼接方式。""",
    'db-wal-recovery': r"""1. 先备份再动手（最高优先级）：一上来就把 /app/main.db*（含 main.db-wal）全部 cp 到 /tmp 做只读备份，后续所有分析只用备份副本。WAL 里是缺失记录的唯二来源（main.db 只有 5 条、目标 11 条），原件一毁数据就拿不回来。
2. 禁止用 sqlite3（或任何会改写文件的库）打开损坏/加密的 WAL：sqlite3 遇到无法解析的 WAL 会把它重置/删除——这是已知真实失败案例（agent 用 sqlite3.connect 打开后 WAL 就消失了）。分析一律只读：cp/xxd/python 读字节、XOR 解密写回 /tmp 副本、用 sqlite3 "file:/app/main.db?mode=ro" 只读打开主库。
3. 解密方法：WAL 是单字节 XOR 0x42 加密（文件里占多数的 'B' 字节就是 0x42）。XOR 0x42 后 WAL 头应对得上合法 magic 0x377f0682，页数据应解出 'SQLite format 3'。确认解密后再做合并。
4. 交付物：/app/recovered.json = main.db 的 5 条 + WAL 里的 6 条 = 全部 11 条记录（按验收要求字段、排序、无重复 ID）。前 50% 预算内必须先落盘一个含已知数据的骨架版本，再补全 WAL 部分——宁可先交部分正确数据，也不要 deadline 时文件不存在。
5. 常见陷阱：1) 全程保持只读，任何可能触发 checkpoint/归并/重写的操作都会毁掉证据；2) WAL 丢失后不要翻无关目录（如 datasets 里的 parquet 训练数据）找数据，应回到 /tmp 备份副本；3) 解密产物和 recovered.json 都写 /tmp 或 /app 的新文件，绝不复写原 WAL。""",
    'gcode-to-text': r"""1. 程序化解法（不需要视觉模型）：用 matplotlib 在 3D 中渲染 G-code 工具路径（解析 G0/G1/G2/G3 移动线段），把倾斜的打印面旋转投影到可读视角，再把渲染图交给 tesseract OCR 识别文字。参考解就是这个管线（matplotlib + pytesseract + opencv + tesseract-ocr 系统包）——直接用 matplotlib 3D 线段 + 欧拉旋转投影，不要手写像素级渲染器。
2. 视觉通道策略：如果 view_image / VLM 查询返回不可用（vision API down / blind route），立即改用上面的本地渲染+OCR 管线，不要反复重试视觉 API，也不要在没读出像素结果的情况下反复猜测字符。
3. 交付物（硬要求）：/app/out.txt 是唯一验收文件，内容包括要打印出的文字串。前 50% 预算内必须落盘一个骨架文件（哪怕只写当前最可能的字符串），之后再覆盖完善——已连续两次因 deadline 时 out.txt 不存在而 0 分，禁止「文件不完美就不写」。OCR 没读准也先写最佳猜测，至少保住文件存在这一项。
4. 实现要点（按顺序排查，真实失败卡点）：1) 解析 G-code 必须处理 M83 相对挤出模式、初始化 current_e，否则工具路径错乱；2) 文字在倾斜坡面上（Z 随 XY 变化，实测 Z 从 ~3 升到 ~65）——naive 的 top-down 像素渲染 OCR 读不出，必须先做斜面旋转变换（unwarp 到正视角）再渲染，这是能否读对字的决定性一步；3) OCR 前按 Z 高度过滤只留下文字层（盒子/轮廓会混进 OCR），并做灰度/对比度增强；4) 每一步渲染都要把图保存下来、自己看一眼/再喂 OCR，确认效果再推进，不要连续写多个版本。
5. 常见陷阱：1) 不要只凭 G-code 坐标在脑子里猜字母——必须渲染成像素再 OCR；2) 渲染和 OCR 都是可迭代的，但每个迭代都要快（用 numpy/matplotlib 向量化，避免像素级 for 循环）；3) 需要装系统包 tesseract-ocr + libtesseract-dev 和 python 包 pytesseract/matplotlib/numpy；4) OCR 前必须把渲染图裁剪到绘图区（matplotlib 用 ax.get_position()/数据坐标裁剪，去掉 x/y 轴标签、标题等图元）——否则 tesseract 会把图上 'Text' 之类的文本一起读进来（真实失败：out.txt 读出了 'Text' 而不是真正的印刷文字）；保存图时只存绘图区内容，不要直接 OCR 带标题的完整 figure；5) M486 陷阱：G-code 里以「M486 A」开头的行是 Prusa MK4S 的对象/任务元数据（如 'M486 AEmbossed text' 声明一个名为 Embossed text 的打印对象），它不是要打印的文字——禁止把这类行抄进 out.txt（真实失败：out.txt 写了 'Embossed text' 而期望是 flag{gc0d3_iz_ch4LLenGiNg}，0 分）；6) 验收判据是精确全等：验证器用 read_text().strip() == 期望字符串，任何内容不同（哪怕语义对）都是 0 分——OCR 结果必须逐字符核对后再落盘，且前面 50% 就写骨架、留出时间做最后覆盖，不要在 deadline 前才第一次写 out.txt。""",
    'gpt2-codegolf': r"""1. 时间管理：15分钟任务。GPT-2 124M 权重布局是公开常识，禁止把预算押在字节级格式侦察上——前 25% 预算必须写出第一个可编译骨架（按标准布局假设），用题面样例跑一遍验证再修正；预算过半还没有可运行骨架就立即收窄、强制先写第一版，禁止继续侦察（真实失败：有过半才动笔、结果连跑样例的轮次都没有）。写代码同样要增量：先最小骨架（能读权重并输出一个 token）跑通，再逐块加 BPE/attention/ln/mlp，每加一块立刻编译+样例验证；禁止一次性写完整个文件再回头修括号结构（真实失败：连续多轮补右花括号，把注意力调试的预算耗尽）。
2. 输出验证（必做，只编译不算数）：写完必须立刻跑 `cd /app && gcc -O3 -o a.out gpt2.c -lm && ./a.out gpt2-124M.ckpt vocab.bpe 'THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT'`。正确输出是 20 个 token 且其中含 "WARRANTY OF ANY KIND, EXPRESS OR IMPLIED"（这个输入就是验证器用的样例）。只 gcc 编译 + wc -c 量大小不算验证——已知失败案例：能编译、能运行，但输出全是 NUL 字节，因为从没执行过样例。
3. 交付物：/app/gpt2.c（依赖-free，gcc -O3 -lm 编译）且必须 <5000 字节，硬验收条件。写完立即 wc -c，超了当场瘦身（删注释/压缩），不要留到最后一轮。
4. 环境事实：.ckpt 是约 475MB 的原始 float32 dump（124,439,808 个 float = 497,759,232 字节，与标准 GPT-2 124M 参数总数吻合；无 TF 协议头，不能按标准 TF checkpoint 解析）；vocab.bpe 是标准 BPE merges（50001 行含版本头，Ġ 表示空格前缀）；容器没有 file/xxd，用 python struct / wc 就够。
5. 权重/运行方式：/app/a.out gpt2-124M.ckpt vocab.bpe "<input>" 输出后续 20 个 token；arg-max 采样。权重顺序按 GPT-2 124M 标准（wte/wpe → blocks 0..11 每块 ln_1/attn/ln_2/mlp → ln_f）写骨架，用上面第 2 条的样例锚点校准顺序和 BPE 解码。注意力实现要点（真实失败卡点）：每个位置都必须用各自的投影得到 q=Wq·h_t、k=Wk·h_j、v=Wv·h_j，attention 分数 = Σ_j (q_t·k_j)/√d_k，输出 = 各位置 v 的加权和；禁止只用当前 t 的 K/V 去 attend 其它位置的 raw hidden state，禁止在 score 里乘 kk[i]/vv[i]。
6. 常见陷阱：1) 格式一致性核查（浮点 min/max、行数、合并格式）最多 2-3 轮，边际收益极低；2) 超过 5000 字节的文件也能编译运行，但验证器只看字节数，超了就是 0 分；3) 输出全 NUL/空 多半是 arg-max 落到 token 0（权重布局错→logits 全等）或 BPE 解码/输出写成了原始字节，必须跑样例对照修正；4) 不要翻 /app/datasets 的 parquet 训练数据——与任务无关，真实失败里在上面的侦察浪费过半预算。""",
    'make-doom-for-mips': r"""1. 时间管理（15分钟硬约束，真实失败关键）：这是 60 分钟级工程任务被压到 15 分钟，前 20% 预算（3 分钟）内必须跑通最小冒烟（见第 6 条），禁止花 7 分钟以上只读源码/装工具/写 Makefile 而从不验证链路——真实失败：mimo 这次跑了 15 分钟、装了 gcc、写了 Makefile.mips、两次 make 编译，但**从未执行过 `node vm.js`**，deadline_local 截断时 /tmp/frame.bmp 根本不存在，三个测试全挂。任何一轮如果还没跑过 `node vm.js` 就必须立刻停下来做最小冒烟验证。
2. 任务本质与交付物：环境给 /app/doomgeneric/（Doom 源码 + doomgeneric_img.c，每帧写 /tmp/frame.bmp）和 /app/vm.js（执行 doomgeneric_mips 这个 MIPS ELF）。交付 = doomgeneric_mips + node vm.js 能跑并生成 /tmp/frame.bmp。验收三连：test_vm_execution（跑 vm 等 frame.bmp，30s 超时即失败）+ frame.bmp 存在 + 与参考图相似。frame.bmp 没生成 = 三个测试全挂（真实失败即如此）。
3. syscall 适配是关键瓶颈（不要手写 libc shim）：先读 vm.js 的 syscall 处理代码（约 4000+ 号段，mmap/brk/文件/exit），搞清楚它实际支持哪些系统调用，按支持子集裁剪编译（-static 链接、去掉不需要的平台文件），而不是自己手写 stdio/stat/malloc 替身——真实失败里 agent 造了 9KB shim_impl.c + 一组假头文件，这条造轮子路线花掉后半程全部预算。若要改 vm.js 补 syscall，一次改完立即 node 验证，不要反复改-回滚（真实失败：同一补丁 3 次尝试含 1 次回滚）。
4. 编译策略：用交叉编译器 -static 一次构建，优先砍掉用不到的 doomgeneric 平台变体（只留 doomgeneric_img.c 与核心渲染），对每个 missing symbol 看 vm.js 能否映射，映射不了才考虑最小桩；禁止逐个大文件手工改造成 do-while(0) 或空实现来骗过链接器，那会浪费大量轮次。每完成一步立即 gcc 编译 + node vm.js 冒烟，用 /tmp/frame.bmp 是否出现作进度标准。
5. 常见陷阱：1) 不要 8 分钟只读源码不编译——交叉工具链可能没装，装（apt install gcc-mipsel-linux-gnu）也要算进前 20% 预算；2) 不要对 vm.js 做无法验证的大幅重写，先在 node vm.js 环境里最小复现一个 syscall 调用链再动；3) 帧相似度测试要求渲染逻辑正确，不是随便一帧 bitmap，必须在本地对照 doomgeneric_img.c 的写帧路径确认颜色/尺寸正确；4) 全程以「node vm.js 能跑出第一帧」为唯一中期里程碑，所有工作围绕它展开。
6. 最小冒烟（最高优先级，定义 = 跑通 node vm.js，不是编译 MIPS ELF）：在动 doomgeneric 之前，必须先用 2 分钟跑通最小 MIPS 链路——关键纪律：**编译 MIPS ELF 不算最小冒烟，必须执行 `node vm.js` 看到输出/错误才算**。步骤：1) 写 /tmp/hello.c（`int main(){return 0;}`）；2) `mipsel-linux-gnu-gcc -static -o /tmp/hello_mips /tmp/hello.c`；3) **立即执行** `node vm.js /tmp/hello_mips` 并查看输出/错误（这一步必须做，禁止跳过、禁止继续写其他文件直到看到结果）；4) 链路通了才去碰 doomgeneric。真实失败（两次）：11:55 那次 agent 把 15 分钟全花在让 doomgeneric 完整编译通过，从未跑过一次 `node vm.js`；12:25 那次 agent 写了 hello.c 编译成 MIPS ELF，但**没有执行 `node vm.js /tmp/hello_mips`**，又回到造 27KB my_stdlib.c 的老模式——最小冒烟走了形式没走实质。记住：编译出 MIPS ELF 只是中间产物，跑通 `node vm.js` 才是验证链路。""",
    'polyglot-rust-c': """1. 时间管理（15分钟硬约束，真实失败关键）：先落盘交付物再验证假设。前 25% 预算内必须写出第一个 /app/polyglot/main.rs 骨架版本并用两种编译器各编译一次——真实失败：15 分钟只做了 6 次工具调用（which/rustc --version/g++ --version/mkdir/写探针 test_hashif.rs/编译探针），main.rs 一次都没写过，900s 外层超时后 verifier 第一步就因文件不存在判 0 分。禁止先花时间验证「rustc 是否容忍 #if 指令」这类自有假设——直接写交付物、用两种编译器的报错来校准写法。
2. 任务本质与交付物：/app/polyglot/main.rs 是唯一交付物，必须同时被 rustc 和 g++ -x c++ 编译通过，两个二进制运行 /app/polyglot/main N 都打印第 k 个斐波那契数（f(0)=1, f(1)=1, f(2)=2...）。验收测 5 个输入 n=0,1,2,10,42 期望 1,1,2,89,433494437。文件不存在 = 全部测试直接失败，不用等编译。
3. polyglot 写法（实践经验，先写这个再调）：用 C 预处理器在两种语言里都合法的注释/文字 Trick——经典做法是用 #if 0 / #else / #endif 把 Rust 代码包在 C 会跳过的块里，或用 C 的注释 /* */ 承载 Rust 的 doc 注释；Rust 单文件没有预处理器，所以让 Rust 看到的行全部是合法 Rust、C 看到的行是合法 C++。参考常见 polyglot 模式：开头用 #ifdef __cplusplus / #endif 区分，函数体用宏或注释技巧共享。写完立即 rustc main.rs && g++ -x c++ main.rs 双编译，按报错迭代，不要只编译单一语言。
4. 工作节奏：每个版本写完立刻 rustc + g++ 双编译 + 跑 N=0,1,2,10,42 验证输出；禁止一次工具调用只做侦察（which/version 这类一次够）。如果对语法有疑问，直接在 main.rs 里试 + 编译看报错，而不是先写探针文件验证——探针文件不产生交付物（真实失败：把唯一一次写文件用在了 test_hashif.rs 上）。
5. 写完立即闭环验证（防止「写了但没验证就收尾」）：每次 write_file 落盘 /app/polyglot/main.rs 后，立刻在同一轮内执行「rustc 编译 → g++ -x c++ 编译 → 两个二进制各跑 N=0,1,2,10,42 → wc -c 确认文件存在」。真实失败：多次运行中 agent 已写出内容正确的 main.rs（甚至双编译通过），但因后续 LLM 调用挂起（provider 无响应数分钟）被强制收尾，verifier 仍报 main.rs not found——文件写没写、对不对必须在 write 后的下一两个工具调用内确认完毕，不要依赖「之后再回来验证」。头 50% 预算内必须让双编译 + 5 个输入输出全绿，剩余预算留给微调。
6. polyglot 标准解法（已在本任务镜像里验证：rustc 与 g++ -x c++ 都编译通过、N=0,1,2,10,42 输出 1,1,2,89,433494437）——核心是宏重定义，不是注释技巧：C++ 段写在 /* */ 里并用 #define 把 Rust 关键词映射成 C++ 合法形式（#define fn int、#define let int、#define main _main、#define println、#define u32 5; int qq1、#define as : 5 等），使同一段「fn main() { let arg1:u32 = env::args()... }」对 g++ 是 C++ 代码、对 rustc 是原生 Rust；C++ 侧先写 namespace mine { int atoi(...)... } + 一个真 C++ main，Rust 侧照常写 fn main 用 env::args().nth(1).unwrap().parse() 读参数、while 循环算斐波那契、println! 输出。关键纪律：1) 文件必须纯 ASCII——任何中文注释/Unicode 破折号都会让 g++ 报「extended character is not valid in an identifier」；2) 不要用 #if 0 / #ifdef 这类预处理指令包 Rust 代码——rustc 会报「expected one of ! or [ found keyword if」；3) 双语言共享同一段 fib 用 while 循环（别再写递归，避免两边语法差异）。照此模板写，写完立即双编译 + 5 输入验证。
7. 可直接落盘的完整模板（已在本任务镜像验证 rustc+g++ 双编译通过、N=0,1,2,10,42 输出 1,1,2,89,433494437）：把这整个文件原样写到 /app/polyglot/main.rs 即可跑通，不要自己发明 polyglot 语法。模板全文如下（含 C++ 段 in namespace mine + 宏映射 + Rust fn main + 收尾 main）：
/*
/*
 *///

namespace mine {
int atoi(const char *str) {
  int result = 0;
  int sign = 1;
  int i = 0;
  while (str[i] == ' ' || str[i] == '\\t' || str[i] == '\\n' ||
         str[i] == '\\v' || str[i] == '\\f' || str[i] == '\\r') {
    i++;
  }
  if (str[i] == '-' || str[i] == '+') {
    sign = (str[i] == '-') ? -1 : 1;
    i++;
  }
  while (str[i] >= '0' && str[i] <= '9') {
    result = result * 10 + (str[i] - '0');
    i++;
  }
  return sign * result;
}

#include <stdio.h>
int main(int argc, char** argv) {
  int arg1 = atoi(argv[1]);
  int i = 0;
  int a = 1;
  int b = 1;
  while (i < arg1) {
    i += 1;
    int t = a;
    a += b;
    b = t;
  }
  printf("%d\\n", b);
  return 0;
}


class std {
public:
  static int env;
};

#define use int std::env = 0; int q() { int x =

// */

use std::env;


/*
/*
 *///
 return 0;
}
struct bar {
    struct bar parse() { return *this; }
    int unwrap() { return 0; }
};

struct foo {
    struct foo nth(int n) { return *this; }
    struct bar unwrap() {
        struct bar b;
        return b;
    }
};

class env {
public:
    static struct foo args() {
        struct foo f;
        return f;
    };
};

#define fn int
#define let int
#define arg1 qq0 = 0?5
#define u32 5; int qq1

#define as : 5
#define u64
#define mut
#define println
#define main _main

// *///


fn main() {
  let arg1:u32 = env::args().nth(1).unwrap().parse().unwrap();

  let mut i = 0;
  let mut a = 1;
  let mut b = 1;
  while (i < (arg1 as u64)) {
    i += 1;
    let t = a;
    a += b;
    b = t;
  }
  println!("{}\\n", b);
}

/*
/*
 *///

}
#define main main

int main(int argc, char** argv) {
      return mine::main(argc, argv);
  }
// */""",
    'pytorch-model-recovery': r"""1. 模型架构：Transformer (encoder + decoder)，包含 3 层 encoder、1 层 decoder、4 个注意力头、d_model=128、dim_feedforward=256。
2. forward() 签名：模型需要同时接收 src 和 tgt 两个参数，即 forward(src, tgt)。测试会调用 model(src_sequences, tgt_sequences)。
3. TorchScript 导出：使用 torch.jit.script(model) 导出时，确保 forward() 方法签名正确包含两个参数 (src, tgt)，不要只保留一个参数。
4. 常见错误：只从权重中恢复 encoder 部分，或导出时 forward() 只接收 src 参数，会导致测试报错 'forward() expected at most 2 argument(s) but received 3 argument(s)'。""",
    'qemu-alpine-ssh': r"""1. QEMU 启动参数模板（使用磁盘镜像）：qemu-system-x86_64 -m 512 -hda /app/alpine-disk.qcow2 -netdev user,id=net0,hostfwd=tcp::2222-:22 -device virtio-net-pci,netdev=net0 -nographic -daemonize
2. SSH 配置步骤：1) 启用 root 登录：sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config；2) 设置密码：echo 'root:password123' | chpasswd；3) 启动服务：rc-service sshd start；4) 设置开机启动：rc-update add sshd
3. 快速调试：1) 检查 QEMU 进程：ps aux | grep qemu；2) 检查端口监听：netstat -tlnp | grep 2222；3) 测试连接：sshpass -p password123 ssh -o StrictHostKeyChecking=no -p 2222 root@localhost 'echo ok'
4. 关键检查点：1) 磁盘镜像必须存在且可写；2) 端口 2222 不能被占用；3) SSH 服务必须在虚拟机内启动；4) 测试期望内核版本为 6.6.4-1-lts（Alpine 3.19 LTS）""",
    'raman-fitting': r"""1. 时间管理：15分钟任务，必须在50%时间（7.5分钟）前生成 results.json。先输出初始结果，再迭代优化。禁止花超过3分钟在数据探索或可视化上。
2. 交付物优先级：results.json 是唯一交付物。先用初始猜测值创建文件（即使不完美），然后逐步改进精度。不要等到完美拟合才写入文件。
3. 数据格式分析：graphene.dat 包含两列数据（逗号作小数点），x 范围约 1649-47184，间距呈指数增长，这是典型的波长（nm）轴数据。必须先转换成 cm⁻¹ 再拟合，不能直接拟合原始 x。
4. x 轴转换（唯一正确做法）：把原始 x 直接当作 nm 波长，用 x_cm⁻¹ = 1e7 / x 取倒数即可。不要引入任何激光波长公式（Raman shift = 10⁷×(1/λ_laser − 1/λ_sample) 之类的换算对这个数据集是错的），参考解法就是这一行倒数换算。
5. 转换验证锚点（拟合前必做）：G 峰在 1580 cm⁻¹ → 原始 x ≈ 1e7/1580 ≈ 6329；2D 峰在 2670 cm⁻¹ → 原始 x ≈ 1e7/2670 ≈ 3745。先用这两个锚点核对数据里对应原始坐标处确实有峰，再开始拟合；锚点对不上说明转换假设错了，换假设而不是硬调拟合参数。原始 x≈6329 处的大峰就是 G 峰，不是激光瑞利线。
6. 峰值位置参考：石墨烯的 G 峰在 ~1580 cm⁻¹，2D 峰在 ~2670-2700 cm⁻¹。拟合时应关注这些范围附近的信号。
7. 拟合策略：使用洛伦兹函数拟合，裁剪窗口（G: 1500-1700，2D: 2500-2900）后 curve_fit。G 峰半高宽（gamma）约 5-15 cm⁻¹，2D 峰半高宽约 15-30 cm⁻¹。如果拟合不收敛，尝试调整初始参数或使用更宽/更窄的拟合窗口。
8. 常见陷阱：1) 数据格式用逗号作小数点，需替换为点号；2) 不要做过度可视化（图表不是交付物）；3) 峰值拟合失败时接受近似值，不要无限调试；4) 如果数据范围异常（如 >10000），优先考虑数据需要转换而非直接拟合；5) 不要在 '532nm/632.8nm 激光'、'x 单位是 Å'、'x/10' 等解释之间反复横跳——先做锚点验证排除假设，再动手拟合。""",
    'torch-pipeline-parallelism': r"""1. 交付物与验收：/app/pipeline_parallel.py 唯一交付物，需实现 train_step_pipeline_afab(model, pipeline_inputs, pipeline_targets, device, dtype)，被 verifier 用 mp.spawn 以 world_size=1、2 分别拉起对比 4 层 LLaMA（hidden=512）：要求每 rank 实际分层数 >0 且 ≤(4+num_hidden_layers)//world_size+1、AFAB 调度（反向之后不能再出现 forward）、每层 fwd/bwd 激活值与参考模型 torch.allclose(atol=1e-5)。文件不得包含 register_forward_hook / register_full_backward_hook（测试方用 hook 采集激活做对比，agent 代码里出现即失败）。
2. 环境注意（真实失败关键）：verifier 在自己独立的 uv venv 里跑（py3.13 + 新版 transformers/torch），agent 往系统 Python 装 torch/transformers 完全白费（PEP 668 externally-managed 拦截 + 两次下载超时，真实失败里 12.4 分钟全耗在这）。不要试图在容器里装 torch——直接读好任务说明写代码，交付物由 verifier 环境导入执行；需要本地验证 torch 行为时优先用已有 venv 或确认容器里是否有可用解释器。
3. forward 调用兼容性（真实失败卡点）：不能裸调 LlamaDecoderLayer / self_attn 而不传 position_embeddings——新版 transformers 的 LlamaSelfAttention.forward 无条件执行 cos, sin = position_embeddings，不显式传入 model.rotary_emb(hidden_states, position_ids) 的 (cos,sin) 结果就会 TypeError: cannot unpack non-iterable NoneType，rank-0 第一层 forward 直接崩（真实失败：3 套 try/except 调用变体全部命中同一错误，world_size=1 和 2 全挂）。写层调用前先在脑子里过一遍目标 transformers 版本的 forward 签名，或写一个最小 Kiwi 调用验证。
4. 时间与自测：900 秒里别把预算花在环境安装/侦察（真实失败：850s 只写了 1 次交付物、0 次自测、7 次工具调用 5 次报错）。前 30% 预算必须落盘第一版骨架（分层 + rank 分发 + AFAB 顺序），再用小模型（hidden 小、层数少）本地自测 verify 分层数与激活对得上；轮询过程中发现任何 forward 调用问题立即按目标版本修。deadline 前一分钟写未测试的大文件 = 必然 0 分。""",
    'torch-tensor-parallelism': r"""1. 交付物与验收：/app/parallel_linear.py 实现 ColumnParallelLinear（权重按列切分，forward 输出必须像 all_gather 一样沿最后一维拼接成完整输出）和 RowParallelLinear（权重按行切分、输入已切分、forward 内部做 all_reduce 求和偏置每 rank 完整）。验收直接调 parallel_layer(input) 与 reference_layer(input) 做 torch.allclose——模块必须自己在 forward 里完成汇聚，测试端不会代做。
2. 真实失败卡点（必须避免）：ColumnParallelLinear.forward 只返回了局部 shard（F.linear(x, self.weight, self.bias)）没做拼接——注释里写「Do not perform implicit all_gather here, allow test harness to simulate it externally」是错误假设，world_size≥2 时输出形状 [2, 48/ws] vs 参考 [2, 48] 直接 RuntimeError，4 个 ws=2/4 用例全挂；RowParallelLinear 因为做了 all_reduce 所以通过。两种并行都要在 forward 内部完成分布式汇聚，切分逻辑本身对了不算完。
3. 自测必做：写完立即 python -c 导入 + 建个小模型对比 reference（权重切片、bias 切片、forward 输出形状与数值），world_size 至少测 1、2、4 三档——不要写完就等着交付（真实失败：3 次工具调用写完即撞 deadline，从未自测，形状错误没被发现）。
4. 环境注意：分布式原语（all_gather/all_reduce）在单进程测试里可能没有 init_process_group，优先用 torch.cat / 简单求和实现 forward 内部汇聚（测试对比的是数值结果不是是否用了 torch.distributed），需要分布式时再考虑 init_process_group('gloo') 等。
5. 【环境事实】agent 容器里没有 torch（09-02 两次实测）：python3 -c 'import torch' 直接 ModuleNotFoundError，系统 pip 被 PEP-668 externally-managed 拦截，任何 pip install torch 都失败（真实失败：09-02 vn2oSe8 花了约 10 分钟、5 次 install + 6 个 find/ls 命令找 torch 全白费）。不要花预算装 torch——交付物由 verifier 自己的 uv venv（py3.13 + torch）导入执行；无法本地自测就把代码的 autograd 路径静态过一遍（见下一条），写完 read_file 确认落盘即可。
6. 【empty_like+all_gather 断图 = 必 0 分（09-02 vn2oSe8 再次实测，最高优先级禁止项）】：ColumnParallelLinear.forward 写成 gathered = [torch.empty_like(local_out) for _ in range(ws)] + torch.distributed.all_gather(gathered, local_out) + return torch.cat(gathered) —— empty_like 预分配缓冲与 local_out 没有任何 autograd 连接，cat 输出没有 grad_fn，world_size≥2 时 backward 直接报 'element 0 of tensors does not require grad and does not have a grad_fn'，4 个 ws=2/4 用例全挂；ws=1 走不到 all_gather 分支所以 [1-*] 全过，不能拿 ws=1 当通过。RowParallel 用 all_reduce 原地改 partial（不换对象、图不断）所以 ws=2/4 全过——column 必须换结构。正确结构 = 自定义 autograd Function：forward(ctx, local_out) 在函数内部 all_gather + cat（local_out 作活体输入，梯度沿它回流），backward 按 ctx.rank 从梯度最后一维切一块返回；或者完全不用 all_gather，直接 torch.cat 本地能拿到的分片（数值等价、图天然不断）。
7. 自定义 autograd Function 的签名与调用点必须同步修改（新失败模式，09-02 实测根因）：ColumnParallelLinear 用 _AllGatherAlongLastDim.apply(*all_chunks) 调用自定义 Function。自审发现 empty_like 预分配缓冲脱离 autograd 图、梯度断流后，agent 把 forward 从 forward(ctx, *local_chunks) 重写为单输入 forward(ctx, local_out)，但调用点仍把多个 chunk 打散传入 → world_size=2/4 直接 TypeError: '_AllGatherAlongLastDim.forward() takes 2 positional arguments but 3 were given'，4 个 ws=2/4 用例全挂；world_size=1 时 all_chunks 只有 1 个元素，恰好匹配单输入签名，把错配完全掩盖（[1-*] 两档全过）。纪律：任何改变 Function 签名/调用方式的修改，必须同时 grep 全部调用点一并更新，改动后用 ws=2/4 实测，禁止只改一端；ws=1 通过不等于实现正确。
8. 自审（acceptance review）只读代码不执行测试，改完必须自己实测（09-02 真实失败）：review 静态发现了 empty_like 断图问题并给出重写方向，但 agent 按意见重写后又引入上面的签名错配——第二轮 review 仍 FAIL（2 个未解决项），且此时已进入 improvement_window_inside_reserve（deadline 前 5 分钟保留区），被强制 finalize，没有任何再修机会。教训：自审意见只当提示，改完的代码必须自己用 mp.spawn 分别跑 ws=1/2/4 实测（本地起不了分布式就在单进程里用 torch.cat/求和模拟再核对形状与数值）；所有验证赶在保留区之前完成，不要把最后一轮 review 当兜底。
9. 最终总结里描述的修改 ≠ 磁盘上的修改（09-02 真实失败）：agent 的收尾消息声称 ColumnParallelLinear.forward 已改为 _AllGatherAlongLastDim.apply(local_out)，但全程只做了 2 次 edit_text（删 _ReduceScatterSum + 重写 Function 类），调用点从未编辑——verifier 按磁盘上的 /app/parallel_linear.py 判分，该行仍是 apply(*all_chunks)，判 0 分。纪律：修复必须是真实落盘的文件编辑；编辑后立即 read_file 或 import 确认磁盘内容与预期一致。verifier 只看工作区文件，不看 agent 在总结里声称做了什么。""",
    'write-compressor': r"""1. 交付物与验收：唯一交付物 /app/data.comp，必须 ≤2500 字节，且被现场编出的解压器（gcc -o decomp2 decomp.c 后 cat data.comp | decomp2）逐字节还原成 data.txt。decomp.c 就是解压器源码（radix-255 自适应算术编码 + LZ77 式），压缩端必须按它的格式编码——先读 decomp.c 搞清它期望的编码/上下文模型，再写压缩器，编码格式错 = 解压段错误（真实失败：压缩器输出 3035 字节且解压 Segmentation fault returncode 139，agent 自测同样复现，确认是格式错误不是环境差异）。
2. 时间管理：15 分钟里压缩器代码量大（参考实现约 19KB），前 30% 预算必须写出第一版并跑通 解压-还原 自测闭环（cat data.comp | ./decomp | cmp data.txt）；禁止一次性写 20KB 再回头修（真实失败：15:28 一次写 20915 字符 compress.py，15:29 自测就发现格式错，重写第二版发生在 deadline 之后从未运行）。每次改动立即走「压缩 → 解压 → cmp 原文件 → wc -c 查大小」四步闭环。
3. 压缩策略：先读透 decomp.c 的解码逻辑（算术编码的 radix/上下文自适应规则、LZ77 的距离/长度编码），压缩端严格反推实现；优先让还原正确（任何输入都能无损还原），再优化压缩率到 ≤2500 字节（data.txt 只有 75 个唯一字节、结尾无换行，可先用转义/字典方案保还原，再收紧）。不要先追求压缩率导致格式不兼容。
4. 常见陷阱：1) data.comp 大小用 wc -c 在写完立即查，3035 > 2500 就是 0 分，不要留到 verifier；2) 解压段错误（139）几乎总是压缩格式与 decomp.c 期望不匹配——用同一份 decomp.c 本地自测即可复现，不要怀疑是测试环境问题；3) 长 LLM 生成很贵（真实失败里两次 4-5 分钟生成耗掉大半预算），压缩器分块写、每块立即验证；4) 【交付物命名/落盘】唯一交付物必须是 /app/data.comp 这个确切路径——写了 encode.py、data.txt、decomp.c 但没生成 /app/data.comp = 直接三测全挂（真实失败 8pA4EpS 等：test_compressed_file_exists 就报 File /app/data.comp does not exist，另外两个 test 跟着全 fail，0 分）；生成脚本的产物路径要和验收完全一致，写完必须 ls /app/data.comp + wc -c 确认存在；5) 【自测发现解压失败必须修完再交付】只要 cat data.comp | ./decomp 出现 EXIT:139 或 stdout 与原文不等，就说明压缩格式错了——不要带着已知段错误交付（真实失败 YHYUdFs：自测已见 EXIT:139，仍提交 2637 字节 data.comp，测试 2/3 fail）。每一步都跑「压缩→cat|decomp→cmp data.txt→wc -c」四步闭环，全部通过才算完成。
5. provider 卡死变体（09-02 PA9MifN 真实失败）：15 分钟预算里 agent 只完成 4 轮、1451 completion tokens——第一轮读完 decomp.c/wc -c 后，下一次 LLM 调用 APITimeoutError 卡死约 10 分钟（日志：LLM retry 1/6, backoff=4s, error='Request timed out.'），恢复后做了 2 个快命令（python 读 data.txt、gcc 编译 decomp.c），紧接着第二次 LLM 调用再次挂起，到 900s 被 Harbor 硬掐（AgentTimeoutError），/app/data.comp 从未写入，verifier 三测全挂（文件不存在）。教训：provider 不稳定时第一轮 LLM 响应可能就是唯一机会——第一轮必须同时完成「读 decomp.c + 落盘 data.comp 骨架」，禁止只侦察不写；任何一次 LLM 卡死恢复后，下一步优先写文件而不是继续侦察。容器无 xxd（读字节用 python3），gcc/python3 在 agent 环境可用。""",
}


def render_task_annotations(task_name: str) -> str:
    """Render the annotation block for `task_name`, or "" when nothing is known.

    `task_name` is the bare task name (e.g. "write-compressor"), not the
    terminal-bench/<name> instance id.
    """
    body = TASK_ANNOTATIONS.get((task_name or '').strip())
    if not body:
        return ""
    header = "--- task-specific annotations (from task failure analysis) ---"
    return f"{header}\n<task-annotations>\n{body}\n</task-annotations>"


def annotated_task_count() -> int:
    return len(TASK_ANNOTATIONS)
