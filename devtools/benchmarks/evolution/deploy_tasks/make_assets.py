#!/usr/bin/env python3
"""生成部署期工作区输入资产（中等复杂度档，确定性、可审计）。

为 deploy_tasks.json 的 12 条 shared 任务各生成一份逼真输入（含脏数据、
缺失值、边界用例），输出到 ``assets/<task_id>/``；同时产出
``assets/manifest.json``（文件 → sha256，供运行时校验与论文附录公开）。

与 GAIA/TB 题面零重叠：全部内容为通用场景人工构造；固定 seed 保证
可复现；不依赖外部文件与网络。
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import random
import struct
import tarfile
import zlib

ASSETS_DIR = pathlib.Path(__file__).resolve().parent / "assets"
SEED = 20260904
rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# 基础素材
# ---------------------------------------------------------------------------

FIRST = ["Alice", "Ben", "Carol", "Devon", "Elena", "Felix", "Grace", "Hiro",
         "Ivy", "Jun", "Kai", "Leila", "Ming", "Noah", "Olga", "Pavel",
         "Qing", "Ravi", "Sofia", "Tomas"]
CITIES = ["Beijing", "Shanghai", "Shenzhen", "Singapore", "Tokyo", "Seoul",
          "London", "Berlin", "Paris", "New York", "Toronto", "Sydney"]
PRODUCTS = ["keyboard", "mouse", "monitor", "headset", "webcam", "cable",
            "dock", "hub", "charger", "speaker", "mic", "stand"]
ACTIONS = ["signup", "login", "search", "view_item", "add_cart", "checkout",
           "payment", "review", "refund", "support_ticket"]
CODES = [f"{rng.randint(100, 599)}" for _ in range(20)]


def write(rel: str, content, *, binary: bool = False) -> None:
    p = ASSETS_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def png_1x1(rgb: tuple[int, int, int]) -> bytes:
    """zlib 手写合法 1x1 PNG（无第三方依赖）。"""
    def chunk(typ: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb)))
            + chunk(b"IEND", b""))


def make_tar_gz(name: str, entries: list[tuple[str, str]]) -> bytes:
    """内存构造 tar.gz（entries = 相对路径 → 文本内容）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, text in entries:
            info = tarfile.TarInfo(rel)
            data = text.encode("utf-8")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# deploy-01：删除 .txt 空行并报告行数
# ---------------------------------------------------------------------------

def gen_01() -> None:
    body = []
    for i in range(1, 81):
        kind = rng.random()
        if kind < 0.12:
            body.append("")
        elif kind < 0.20:
            body.append("   ")          # 空白行（非空行，不应被删）
        elif kind < 0.85:
            body.append(f"record_{i:03d} value={rng.randint(0, 9999)}"
                        f" tag={rng.choice(['alpha', 'beta', 'gamma'])}")
        else:
            body.append(f"note line {i} — free text {rng.randint(10, 99)}")
    write("deploy-01/a.txt", "\n".join(body))
    # b.txt：一半以上是空行（压力用例）
    b = ["" if rng.random() < 0.6 else f"payload-{i}" for i in range(60)]
    write("deploy-01/b.txt", "\n".join(b))
    # c.txt：全空文件（边界：0 行）
    write("deploy-01/c.txt", "")


# ---------------------------------------------------------------------------
# deploy-02：CSV 小写化清洗 + 非空计数
# ---------------------------------------------------------------------------

def gen_02() -> None:
    rows = ["name,email,region,orders"]
    for i in range(200):
        name = rng.choice(FIRST)
        if rng.random() < 0.3:
            name = name.upper()         # 脏数据：大小写混合
        email = f"{name.lower()}{i}@example.com"
        if rng.random() < 0.08:
            email = ""                  # 缺失字段
        region = rng.choice(CITIES)
        if rng.random() < 0.05:
            region = f'"{region}, CN"'  # 引号内逗号
        orders = rng.randint(0, 120)
        if rng.random() < 0.04:
            orders = ""                 # 缺失数值
        rows.append(f"{name},{email},{region},{orders}")
    rows.append("")                     # 尾部空行（脏）
    write("deploy-02/data.csv", "\n".join(rows))


# ---------------------------------------------------------------------------
# deploy-03：最大 3 个文件
# ---------------------------------------------------------------------------

def gen_03() -> None:
    files = []
    for i in range(9):
        size = rng.choice([500, 2000, 8000, 32000, 128000, 1_000_000])
        text = ("".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789 ")
                        for _ in range(size // 8)))
        name = f"{rng.choice(['alpha', 'beta', 'gamma', 'delta'])}_{i:02d}.txt"
        files.append((name, text))
    files[3] = (files[3][0], files[1][1])   # 并列大小（边界：取第几大的歧义）
    for i in range(len(files)):
        for j in range(i):
            if files[j][0] == files[i][0]:
                files[i] = (f"dup_{i:02d}_{files[i][0]}", files[i][1])
    for name, text in files:
        write(f"deploy-03/{name}", text)


# ---------------------------------------------------------------------------
# deploy-04：TODO 行抽取
# ---------------------------------------------------------------------------

def gen_04() -> None:
    notes_tasks = {
        "frontend": ["homepage", "checkout", "search_bar"],
        "backend": ["auth", "billing", "queue"],
        "ops": ["deploy", "monitoring"],
    }
    for area, files in notes_tasks.items():
        for f in files:
            lines = []
            for i in range(1, 25):
                kind = rng.random()
                if kind < 0.15:
                    lines.append(f"TODO: {rng.choice(['fix bug', 'add test', 'refactor',
                                                      'update doc', 'remove dead code'])} "
                                 f"in {area}/{f} (#{rng.randint(100, 999)})")
                elif kind < 0.6:
                    lines.append(f"implemented {rng.choice(['auth flow', 'pagination',
                                                            'error handler'])} step {i}")
                else:
                    lines.append(f"## note {i}")
            write(f"deploy-04/notes/{area}/{f}.md", "\n".join(lines) + "\n")
    # 无 TODO 的文件（边界）
    write("deploy-04/notes/archive/old.md", "\n".join(f"done {i}" for i in range(10)))


# ---------------------------------------------------------------------------
# deploy-05：图片重命名（合法 PNG + JPEG 魔数）
# ---------------------------------------------------------------------------

def gen_05() -> None:
    colors = [(210, 30, 30), (30, 210, 60), (30, 90, 210), (240, 200, 10)]
    for i in range(12):
        if i % 4 == 3:
            # JPEG：合法魔数 + 填充（重命名任务不需要解码；agent 用 view_image 时
            # 只能识别这一张为无效 JPEG —— 属预期边界）
            data = b"\xff\xd8\xff\xe0" + bytes(rng.randrange(256) for _ in range(64))
            name = f"shot_{rng.randint(1000, 9999)}.{rng.choice(['jpg', 'jpeg'])}"
            write(f"deploy-05/images/{name}", data, binary=True)
        else:
            write(f"deploy-05/images/img_{i:03d}.png", png_1x1(rng.choice(colors)),
                  binary=True)


# ---------------------------------------------------------------------------
# deploy-06：日志错误码统计
# ---------------------------------------------------------------------------

def gen_06() -> None:
    lines = []
    for i in range(400):
        ts = f"2026-0{rng.randint(1, 9)}-{rng.randint(10, 28):02d}T"
        ts += f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        svc = rng.choice(["api-gateway", "auth-svc", "billing-svc", "search-svc", "queue-worker"])
        if rng.random() < 0.45:
            code = rng.choice(CODES)
            lines.append(f"{ts} ERROR {code} {svc} request failed: {rng.choice(['timeout', 'db down', '5xx', 'throttled'])}")
        elif rng.random() < 0.30:
            lines.append(f"{ts} WARN {svc} slow query {rng.randint(1, 999)}ms")
        else:
            lines.append(f"{ts} INFO {svc} handled {rng.randint(1, 99)} reqs")
    # 边界：格式异常行（无 ERROR 前缀但含 code）
    lines.append(f"2026-09-04T00:00:00 weird line mentioning code 503 without prefix")
    lines.append("corrupted log line without timestamp")
    write("deploy-06/app.log", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# deploy-07：合并同名文件（a 内容在前）
# ---------------------------------------------------------------------------

def gen_07() -> None:
    names = ["config", "manifest", "readme", "data", "notes"]
    for base in names:
        a = "\n".join(f"{base}-a {i}" for i in range(1, 8)) + "\n"
        b = "\n".join(f"{base}-b {i}" for i in range(1, 8)) + "\n"
        write(f"deploy-07/a/{base}.txt", a)
        if base == "notes":
            b = ""                      # 边界：b 同名文件为空
        write(f"deploy-07/b/{base}.txt", b)
    write("deploy-07/a/only_a.txt", "only in a\n")
    write("deploy-07/b/only_b.txt", "only in b\n")


# ---------------------------------------------------------------------------
# deploy-08：JSON 数字字段汇总
# ---------------------------------------------------------------------------

def gen_08() -> None:
    for i in range(14):
        payload = {
            "id": i,
            "meta": {"name": rng.choice(PRODUCTS), "region": rng.choice(CITIES)},
            "values": {
                "amount": rng.choice([0, 12.5, -3, 99.99, 1_000_000, 0.001, 17]),
                "tax": round(rng.random() * 10, 2),
                "shipping": rng.choice([0, 5, 15.5, None]),
            },
        }
        write(f"deploy-08/data/entry_{i:02d}.json",
              json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    # 边界：一个坏 JSON
    write("deploy-08/data/entry_bad.json", '{"id": 99, "values": { "amount": ')


# ---------------------------------------------------------------------------
# deploy-09：首字母大写
# ---------------------------------------------------------------------------

def gen_09() -> None:
    lines = []
    for i in range(180):
        kind = rng.random()
        if kind < 0.10:
            lines.append("")                        # 空行
        elif kind < 0.20:
            lines.append(f"{rng.randint(1000, 9999)} {rng.choice(['suite', 'room', 'floor', 'apt'])}")  # 数字开头
        elif kind < 0.25:
            lines.append(rng.choice(["ALREADY UPPER", "MIXED Case line", "   leading spaces"]))
        else:
            words = [rng.choice(FIRST + CITIES + PRODUCTS).lower() for _ in range(rng.randint(2, 8))]
            lines.append(" ".join(words))
    write("deploy-09/sentences.txt", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# deploy-10：config.ini 重复 section
# ---------------------------------------------------------------------------

def gen_10() -> None:
    sections = {
        "server": {"host": "0.0.0.0", "port": "8080", "workers": "4"},
        "cache": {"backend": "redis", "ttl": "300", "maxsize": "1024"},
        "logging": {"level": "info", "file": "/var/log/app.log"},
        "queue": {"driver": "sqs", "concurrency": "8"},
    }
    order = ["server", "cache", "logging", "server", "queue", "cache", "server"]
    lines = []
    for sec in order:
        lines.append(f"[{sec}]")
        kv = dict(sections[sec])
        if sec == "server" and lines.count(f"[server]") == 2:
            kv["port"] = "9090"                     # 重复 section 内的差异（合并来源证据）
        for k, v in kv.items():
            lines.append(f"{k} = {v}")
        lines.append("")
    write("deploy-10/config.ini", "\n".join(lines))


# ---------------------------------------------------------------------------
# deploy-11：tar.gz 解压 + 顶层条目数
# ---------------------------------------------------------------------------

def gen_11() -> None:
    a = make_tar_gz("a.tar.gz", [(f"flat_{i}.dat", f"data {i}") for i in range(1)])
    b = make_tar_gz("b.tar.gz", [(f"pkg-{i}/file{i}.txt", f"x {i}") for i in range(1, 4)])
    c = make_tar_gz("c.tar.gz", [(f"mod{i}/sub/job{i}.py", f"print({i})") for i in range(1, 9)])
    d = make_tar_gz("d.tar.gz", [("empty.dat", "")])     # 0 字节文件（边界）
    write("deploy-11/arch/a.tar.gz", a, binary=True)
    write("deploy-11/arch/b.tar.gz", b, binary=True)
    write("deploy-11/arch/c.tar.gz", c, binary=True)
    write("deploy-11/arch/d.tar.gz", d, binary=True)


# ---------------------------------------------------------------------------
# deploy-12：域名统计
# ---------------------------------------------------------------------------

def gen_12() -> None:
    domains = ["example.com", "test.org", "sample.net", "demo.io", "internal.dev",
               "cdn.example.com", "api.test.org", "static.sample.net",
               "staging.demo.io", "grafana.internal.dev"]
    lines = []
    for i in range(700):
        dom = rng.choice(domains)
        port = "" if rng.random() < 0.9 else f":{rng.randint(1024, 9999)}"
        path = "/".join(rng.choice(["api", "v1", "v2", "assets", "files", "docs"])
                        for _ in range(rng.randint(1, 4)))
        scheme = rng.choice(["https", "http"])
        lines.append(f"{scheme}://{dom}{port}/{path}/{rng.randint(100000, 999999)}")
    lines.append("http://broken-url-no-host")           # 畸形行（边界）
    write("deploy-12/url_links.txt", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# manifest + main
# ---------------------------------------------------------------------------

def build_manifest() -> dict:
    entries = {}
    for p in sorted(ASSETS_DIR.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            entries[str(p.relative_to(ASSETS_DIR))] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return {"seed": SEED, "generated": True, "files": entries}


def main() -> int:
    for gen in (gen_01, gen_02, gen_03, gen_04, gen_05, gen_06,
                gen_07, gen_08, gen_09, gen_10, gen_11, gen_12):
        gen()
    manifest = build_manifest()
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = len(manifest["files"])
    total = sum(1 for _ in ASSETS_DIR.rglob("*") if _.is_file())
    print(f"assets ok: {ASSETS_DIR}  manifest files={n}  total files={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())