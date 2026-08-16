# 项目环境激活脚本
# 用法（PowerShell，注意前面有点号 source 执行）：
#   . .\activate.ps1                    # 只加载 .env（默认）
#   . .\activate.ps1 -EnvFile .env.gaia # 额外叠加一个扩展环境文件（覆盖 .env 同名变量）
#   . .\activate.ps1 -EnvFile .env.dev  # 想用哪个环境就指定哪个
# 作用：
#   1. 加载 .env（基础模型配置）；传了 -EnvFile 再叠加该文件（后加载覆盖）
#   2. 把 .env 里的模型/API 配置同步到 settings.json（server 实际读取）
#   3. 激活 .venv 虚拟环境
param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$syncScript = Join-Path $root 'scripts\sync_env_settings.py'

# 强制 UTF-8：仓库文件全部 UTF-8，中文 Windows 默认 GBK 会解码失败（read_text/subprocess）
$env:PYTHONUTF8 = '1'

function Load-EnvFile([string]$Path) {
    $loaded = 0
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
            $loaded++
        }
    }
    Write-Host ("loaded {0} ({1} vars)" -f (Split-Path $Path -Leaf), $loaded) -ForegroundColor DarkGray
}

# ---- 1. 加载 .env（必选），可选叠加扩展文件 ----
$baseEnv = Join-Path $root '.env'
if (Test-Path $baseEnv) {
    Load-EnvFile $baseEnv
} else {
    Write-Warning ".env not found: $baseEnv"
}
if ($EnvFile) {
    $extra = $EnvFile
    if (-not [System.IO.Path]::IsPathRooted($extra)) {
        $extra = Join-Path $root $extra
    }
    if (Test-Path $extra) {
        Load-EnvFile $extra
    } else {
        Write-Warning "env file not found, skipped: $extra"
    }
}

# ---- 2. 同步 .env -> settings.json ----
if (Test-Path $venvPython) {
    if (Test-Path $syncScript) {
        Write-Host 'Syncing .env -> settings.json ...' -ForegroundColor DarkGray
        & $venvPython $syncScript
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "env sync reported an error; continuing to activate anyway"
        }
    }
} else {
    Write-Warning "venv python not found: $venvPython"
}

# ---- 3. 激活虚拟环境 ----
& (Join-Path $root '.venv\Scripts\Activate.ps1')
