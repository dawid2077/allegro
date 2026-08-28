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
      in {
        devShells.default = pkgs.mkShell {
          name = "allegro-evaluate-dev";
          buildInputs = with pkgs; [
            python
            uv
            libnss3
            libnspr4
            atk
            at-spi2-core
            libcups
            libdrm
            libxkbcommon
            libxcomposite
            libxdamage
            libxfixes
            libxrandr
            mesa
            alsa-lib
            libxshmfence
            libxss
            libgconf
            nss
            nspr
            dbus
            fontconfig
            freetype
            harfbuzz
            gcc
            make
            cmake
            pkg-config
          ];

          shellHook = ''
            export UV_SYSTEM_PYTHON=1

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