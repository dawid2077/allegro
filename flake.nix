{
  description = "Allegro Evaluate - Search Allegro with natural language and evaluate listings via LLMs";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        uv = pkgs.uv;
        playwright-deps = pkgs.playwright-deps;
      in {
        devShells.default = pkgs.mkShell {
          name = "allegro-evaluate-dev";
          buildInputs = with pkgs; [
            python
            uv
            playwright-deps
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
            pkgs.gcc
            pkgs.make
            pkgs.cmake
            pkgs.pkg-config
          ];

          shellHook = ''
            export UV_SYSTEM_PYTHON=1
            export PLAYWRIGHT_BROWSERS_PATH="${playwright-deps}/lib/playwright"
            export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="${playwright-deps}/lib/playwright/chromium-*/chrome-linux/chrome"

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
        };

        # Also provide a Python package build
        packages.default = pkgs.python311Packages.buildPythonPackage {
          pname = "allegro-evaluate";
          version = "0.1.0";
          src = self;
          format = "pyproject.toml";
          checkInputs = with pkgs; [ pytest ];
          propagatedBuildInputs = with pkgs; [
            python311Packages.typer
            python311Packages.pydantic
            python311Packages.pydantic-settings
            python311Packages.httpx
            python311Packages.structlog
            python311Packages.playwright
            python311Packages.rich
          ];
          doCheck = false;
        };
      });
}