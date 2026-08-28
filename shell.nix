{ pkgs ? import <nixpkgs> {} }:

let
  # Use a stable nixpkgs version for reproducibility
  python = pkgs.python311;
  uv = pkgs.uv;
  playwright-deps = pkgs.playwright-deps;
in
pkgs.mkShell {
  name = "allegro-evaluate-dev";
  buildInputs = with pkgs; [
    python
    uv
    playwright-deps
    # System dependencies for Playwright/Chromium
    pkgs.libnss3
    pkgs.libnspr4
    pkgs.atk
    pkgs.at-spi2-core
    pkgs.libcups
    pkgs.libdrm
    pkgs.libxkbcommon
    pkgs.libxcomposite
    pkgs.libxdamage
    pkgs.libxfixes
    pkgs.libxrandr
    pkgs.mesa
    pkgs.alsa-lib
    # Build tools
    pkgs.gcc
    pkgs.make
    pkgs.cmake
    pkgs.pkg-config
  ];

  shellHook = ''
    export UV_SYSTEM_PYTHON=1
    export PLAYWRIGHT_BROWSERS_PATH="${playwright-deps}/lib/playwright"
    export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="${playwright-deps}/lib/playwright/chromium-*/chrome-linux/chrome"

    # Auto-install Python deps on shell enter if not already done
    if [ ! -d ".venv" ] || [ ! -f ".venv/pyvenv.cfg" ]; then
      echo "Creating virtual environment and installing dependencies..."
      uv venv --python $(which python3.11) .venv
      source .venv/bin/activate
      uv pip install -e ".[dev]"
      playwright install chromium --with-deps
    else
      source .venv/bin/activate
    fi

    echo "allegro-evaluate dev shell ready"
    echo "Run: allegro-evaluate --help"
  '';
}