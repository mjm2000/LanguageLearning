{
  description = "Latin core vocabulary: build declensions and read words aloud";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python313;

        pythonPackages = pkgs.callPackage ./python-packages.nix {
          inherit python;
          fetchurl = pkgs.fetchurl;
        };

        pythonEnv = python.withPackages (_: [
          pythonPackages.latincy-lexicon
          pythonPackages.edge-tts
          pythonPackages.orthography2ipa
          pythonPackages.openai
        ]);

        latin = pkgs.stdenvNoCC.mkDerivation {
          pname = "latin";
          version = "0.1.0";
          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];

          dontConfigure = true;
          buildPhase = "true";

          installPhase = ''
            runHook preInstall

            mkdir -p $out/bin $out/share/latin
            cp ${./build_vocabulary.py} $out/share/latin/build_vocabulary.py
            cp ${./tts_engines.py} $out/share/latin/tts_engines.py
            cp ${./read_aloud.py} $out/share/latin/read_aloud.py
            cp ${./study.py} $out/share/latin/study.py
            cp ${./study_sentences.py} $out/share/latin/study_sentences.py
            cp ${./dcc-core-vocabulary.csv} $out/share/latin/dcc-core-vocabulary.csv
            cp ${./latin-core-1000.json} $out/share/latin/latin-core-1000.json
            cp ${./latin-core-1000.csv} $out/share/latin/latin-core-1000.csv

            makeWrapper ${pythonEnv}/bin/python $out/bin/latin-read \
              --add-flags $out/share/latin/read_aloud.py \
              --prefix PATH : "${pkgs.ffmpeg}/bin" \
              --set LATIN_ROOT $out/share/latin \
              --set PYTHONPATH $out/share/latin

            makeWrapper ${pythonEnv}/bin/python $out/bin/latin-study \
              --add-flags $out/share/latin/study.py \
              --set LATIN_ROOT $out/share/latin \
              --set PYTHONPATH $out/share/latin

            makeWrapper ${pythonEnv}/bin/python $out/bin/latin-build \
              --add-flags $out/share/latin/build_vocabulary.py \
              --prefix PATH : "${pythonEnv}/bin" \
              --set LATIN_ROOT $out/share/latin

            cat > $out/bin/latin-build-analyzer <<EOF
            #!${pkgs.bash}/bin/bash
            set -euo pipefail
            root="''${LATIN_ROOT:-$out/share/latin}"
            mkdir -p "''${root}/data/json"
            exec ${pythonEnv}/bin/latincy-lexicon build --output-dir "''${root}/data/json"
            EOF
            chmod +x $out/bin/latin-build-analyzer

            runHook postInstall
          '';
        };
      in
      {
        packages = {
          default = latin;
          inherit latin;
        };

        apps = {
          default = {
            type = "app";
            program = "${latin}/bin/latin-read";
          };
          read = {
            type = "app";
            program = "${latin}/bin/latin-read";
          };
          study = {
            type = "app";
            program = "${latin}/bin/latin-study";
          };
          build = {
            type = "app";
            program = "${latin}/bin/latin-build";
          };
          build-analyzer = {
            type = "app";
            program = "${latin}/bin/latin-build-analyzer";
          };
        };

        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            pythonEnv
            ffmpeg
            curl
            latin
          ];

          shellHook = ''
            export LATIN_ROOT="$PWD"
            export PATH="${latin}/bin:$PATH"

            echo "Latin vocabulary dev shell"
            echo "  nix run .#read              # replay most recent batch"
            echo "  nix run .#read -- -n        # next 10 words"
            echo "  nix run .#study             # English → Latin drill"
            echo "  latin-build-analyzer && latin-build"
          '';
        };

        formatter = pkgs.nixpkgs-fmt;
      });
}
