# Install locally for the current user; no administrator or profile changes.
$ErrorActionPreference = 'Stop'

try {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $UvPath = if ($UvCommand) { $UvCommand.Source } else { Join-Path $HOME '.local/bin/uv.exe' }
    if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) {
        Write-Host 'Installing uv for your user from astral.sh...'
        $Installer = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName() + '.ps1')
        $PreviousInstallDir = $env:UV_INSTALL_DIR
        $PreviousNoModify = $env:UV_NO_MODIFY_PATH
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri 'https://astral.sh/uv/install.ps1' -OutFile $Installer -UseBasicParsing
            $env:UV_INSTALL_DIR = Join-Path $HOME '.local/bin'
            $env:UV_NO_MODIFY_PATH = '1'
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer
            if ($LASTEXITCODE -ne 0) { throw 'uv installation failed.' }
        } finally {
            $env:UV_INSTALL_DIR = $PreviousInstallDir
            $env:UV_NO_MODIFY_PATH = $PreviousNoModify
            Remove-Item -LiteralPath $Installer -Force -ErrorAction SilentlyContinue
        }
    }

    & $UvPath --version
    if ($LASTEXITCODE -ne 0) { throw 'uv is not working.' }
    Write-Host 'Installing Uthana MCP with Python 3.12 (downloaded by uv if needed)...'
    & $UvPath tool install --python 3.12 uthana-mcp
    if ($LASTEXITCODE -ne 0) { throw 'MCP installation failed.' }
    $BinDir = & $UvPath tool dir --bin
    if ($LASTEXITCODE -ne 0) { throw 'Could not locate installed commands.' }
    $Server = Join-Path $BinDir 'uthana-mcp.exe'
    Write-Host "MCP server command: $Server"
    Write-Host 'Use that absolute command in your host configuration with no arguments.'

    $KeyFile = Join-Path $HOME '.config/uthana/production-key'
    if (Test-Path -LiteralPath $KeyFile) {
        Write-Host "Keeping existing key file: $KeyFile"
        Write-Host 'The server will check its permissions when used.'
    } else {
        & (Join-Path $BinDir 'uthana-mcp-setup.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Key setup did not complete. The MCP package is installed; rerun setup when ready.' }
    }
    Write-Host "Set UTHANA_API_KEY_FILE to: $KeyFile"
    Write-Host 'Restart your MCP host after configuring it.'
} catch {
    Write-Error $_
    exit 1
}
