{ python, fetchurl }:

let
  inherit (python.pkgs)
    buildPythonPackage
    setuptools
    numpy
    langcodes
    aiohttp
    certifi
    tabulate
    typing-extensions
    openai
    ;

  ovos-spec-tools = buildPythonPackage rec {
    pname = "ovos-spec-tools";
    version = "1.11.1a1";
    pyproject = true;

    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/06/c3/afb159a113b3a3edaa5ff4849a1214ef9c58a8e7960d580008cf319e27e6/ovos_spec_tools-${version}.tar.gz";
      hash = "sha256-iXfxvHC3dZa99z3xvElK2ksKxTEHJN8MLOPXtOXKiKI=";
    };

    nativeBuildInputs = [ setuptools ];
    doCheck = false;
  };

  latincy-lexicon = buildPythonPackage rec {
    pname = "latincy-lexicon";
    version = "0.11.1";
    format = "wheel";

    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/9c/d8/6582d2665c6ece2484641198e551a3e13faeabc83a8d256b2a6fca70fcb6/latincy_lexicon-${version}-py3-none-any.whl";
      hash = "sha256-sY6grrHFHlnTCXBSv1I7g+VwmZd1v0a8zA+M5T8lYng=";
    };

    doCheck = false;
  };

  edge-tts = buildPythonPackage rec {
    pname = "edge-tts";
    version = "7.2.8";
    format = "wheel";

    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/8c/2b/a8cb687b92a2690d2ad171f0c2fd1c8f18690363cca7618bab2bbe4cdf2b/edge_tts-${version}-py3-none-any.whl";
      hash = "sha256-Nh/kjOfvYTrb4w9mTjdl3XECnGy1dCcnnv+K1t8ushE=";
    };

    propagatedBuildInputs = [
      aiohttp
      certifi
      tabulate
      typing-extensions
    ];

    doCheck = false;
  };

  orthography2ipa = buildPythonPackage rec {
    pname = "orthography2ipa";
    version = "7.30.0";
    format = "wheel";

    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/7a/92/723919fa61e404168e8c202875c5e7be535751e4e0cb3bdd64bb76142702/orthography2ipa-${version}-py3-none-any.whl";
      hash = "sha256-7FQTF1h5RR/+hU0XmocAlqf/ZlxMiBtPo9ow+jKtO2c=";
    };

    propagatedBuildInputs = [
      numpy
      langcodes
      ovos-spec-tools
    ];

    doCheck = false;
  };
in
{
  inherit latincy-lexicon edge-tts orthography2ipa ovos-spec-tools openai;
}
