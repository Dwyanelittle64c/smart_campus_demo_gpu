param(
    [string]$Environment = 'smart-campus-gpu-runtime',
    [string]$Cuda = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1',
    [ValidatePattern('^\d+\.\d+(\+PTX)?$')][string]$Architecture = '8.6',
    [ValidatePattern('^\d+\.\d+$')][string]$MsvcVersion = '14.29'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $Cuda 'bin\nvcc.exe'))) { throw '未找到 CUDA 12.1 的 nvcc.exe；请安装 Toolkit 或用 -Cuda 指定实际路径' }
if (-not (Test-Path -LiteralPath 'third_party/gsplat/gsplat/cuda/csrc/third_party/glm/glm/glm.hpp')) { throw 'gsplat 或 GLM 子模块未初始化；请先执行 git submodule update --init --recursive' }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $vswhere)) { throw '未找到 Visual Studio 安装器；请先按 README 安装 C++ Build Tools' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw '未找到已有 MSVC x64 工具链；请先确认 Visual Studio C++ 工作负载' }
$vcvars = Join-Path $installation 'VC\Auxiliary\Build\vcvars64.bat'
$environmentLines = & cmd.exe /d /c "call `"$vcvars`" -vcvars_ver=$MsvcVersion >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'vcvars64 初始化失败，尚未开始 CUDA 编译' }
foreach ($line in $environmentLines) {
    if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
$env:CUDA_HOME = $Cuda
$env:CUDA_PATH = $Cuda
$env:PATH = "$Cuda\bin;$env:PATH"
$env:TORCH_CUDA_ARCH_LIST = $Architecture
$env:MAX_JOBS = '2'
$env:DISTUTILS_USE_SDK = '1'
$env:MSSdk = '1'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path docs/setup | Out-Null
$started = Get-Date
$timer = [Diagnostics.Stopwatch]::StartNew()
conda run --no-capture-output -n $Environment python -m pip install ./third_party/gsplat --no-build-isolation --no-deps -v *>&1 | Tee-Object docs/setup/gsplat-build-windows.log
if ($LASTEXITCODE -ne 0) { throw 'gsplat 编译失败，请查看 docs/setup/gsplat-build-windows.log' }
$timer.Stop()
@{started=$started.ToString('o');seconds=$timer.Elapsed.TotalSeconds;environment=$Environment;cuda=$Cuda;msvc=$MsvcVersion;architecture=$Architecture;note='若已有构建目录，可能复用已有 object'} | ConvertTo-Json | Set-Content -Encoding utf8 docs/setup/gsplat-build-timing.json
