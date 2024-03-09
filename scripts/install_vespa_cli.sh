#!/usr/bin/env bash

set -ex

VERSION="8.315.19"
OS="$(uname -s)"
ARCH="$(uname -m)"

if [ "$OS" == "Linux" ]; then
  OS="linux"
elif [ "$OS" == "Darwin" ]; then
  OS="darwin"
else
  echo "Unsupported OS: $OS"
  exit 1
fi

if [ "$ARCH" == "x86_64" ]; then
  ARCH="amd64"
elif [ "$ARCH" == "arm64" ]; then
  ARCH="arm64"
else
  echo "Unsupported architecture: $ARCH"
  exit 1
fi

VESPA_DIRNAME='vespa-cli_'$VERSION'_'$OS'_'$ARCH

wget 'https://github.com/vespa-engine/vespa/releases/download/v'$VERSION'/'$VESPA_DIRNAME'.tar.gz'
tar xvzf $VESPA_DIRNAME.tar.gz
rm $VESPA_DIRNAME.tar.gz
mv $VESPA_DIRNAME/bin/vespa /usr/local/bin/vespa
rm -r $VESPA_DIRNAME
