{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  uv = pkgs.uv;
in
pkgs.mkShell {
  name = "allegro-evaluate-dev";
  buildInputs = with pkgs; [
    python
    uv
  ];

  shellHook = ''
    export UV_SYSTEM_PYTHON=1

    # Use python -m venv instead of uv venv to avoid nix store immutability issues
    if [ ! -d ".venv" ] || [ ! -f ".venv/pyvenv.cfg" ]; then
      echo "Creating virtual environment and installing dependencies..."
      python -m venv .venv
      source .venv/bin/activate
      uv pip install -e ".[dev]"
      .venv/bin/playwright install chromium
    else
      source .venv/bin/activate
    fi

    echo "allegro-evaluate dev shell ready"
    echo "Run: allegro-evaluate --help"
  '';
}