{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  uv = pkgs.uv;
  xorg = pkgs.xorg;
in
pkgs.mkShell {
  name = "allegro-evaluate-dev";
  buildInputs = with pkgs; [
    python
    uv
    # System dependencies for Playwright/Chromium (greenlet, browsers)
    gcc
    nss
    nspr
    atk
    at-spi2-core
    cups
    libdrm
    libxkbcommon
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXfixes
    xorg.libXrandr
    xorg.libXScrnSaver
    xorg.libXcursor
    xorg.libXi
    xorg.libXtst
    mesa
    alsa-lib
    libxshmfence
    dbus
    fontconfig
    freetype
    harfbuzz
  ];

  shellHook = ''
    export UV_SYSTEM_PYTHON=1

    # Set library path so venv can find nix store libs (crucial for Playwright)
    export LD_LIBRARY_PATH="${pkgs.gcc}/lib:${pkgs.mesa}/lib:${pkgs.alsa-lib}/lib:${pkgs.libxshmfence}/lib:${pkgs.libdrm}/lib:${pkgs.libxkbcommon}/lib:${pkgs.xorg.libXcomposite}/lib:${pkgs.xorg.libXdamage}/lib:${pkgs.xorg.libXfixes}/lib:${pkgs.xorg.libXrandr}/lib:${pkgs.xorg.libXScrnSaver}/lib:${pkgs.xorg.libXcursor}/lib:${pkgs.xorg.libXi}/lib:${pkgs.xorg.libXtst}/lib:${pkgs.nss}/lib:${pkgs.nspr}/lib:${pkgs.atk}/lib:${pkgs.at-spi2-core}/lib:${pkgs.cups}/lib:${pkgs.dbus}/lib:${pkgs.fontconfig}/lib:${pkgs.freetype}/lib:${pkgs.harfbuzz}/lib:$LD_LIBRARY_PATH"

    # Use python -m venv with --system-site-packages for Nix-managed Python
    if [ ! -d ".venv" ] || [ ! -f ".venv/bin/python" ]; then
      echo "Creating virtual environment..."
      python -m venv .venv --system-site-packages
      source .venv/bin/activate
      echo "Installing Python dependencies..."
      uv pip install -e ".[dev]"
      echo "Installing Playwright browsers..."
      .venv/bin/playwright install chromium
    else
      source .venv/bin/activate
    fi

    echo "allegro-evaluate dev shell ready (using uv)"
    echo "Run: allegro-evaluate --help"
  '';
}