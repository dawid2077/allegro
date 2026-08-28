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

    # Auto-install Python deps on shell enter if not already done
    if [ ! -d ".venv" ] || [ ! -f ".venv/pyvenv.cfg" ]; then
      echo "Creating virtual environment and installing dependencies..."
      uv venv --python $(which python3.11) .venv
      source .venv/bin/activate
      uv pip install -e ".[dev]"
      playwright install chromium
    else
      source .venv/bin/activate
    fi

    echo "allegro-evaluate dev shell ready (uv + python only)"
    echo "Run: allegro-evaluate --help"
  '';
}