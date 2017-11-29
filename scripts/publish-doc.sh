#!/bin/sh

set -e

REPO=${REPO:-$(git remote get-url origin)}
BRANCH=${BRANCH:-gh-pages}
DOCPATH="$PWD/doc/build"
SITEPATH=/tmp/doc-site

# Build
make doc

# Fetch site repository / branch
rm -rf $SITEPATH
git clone --branch=$BRANCH --single-branch $REPO $SITEPATH
cd $SITEPATH

# Update
git rm -r .
cp -r "$DOCPATH"/* .
touch .nojekyll
git add -A

# Publish
git commit -m "Update documentation"
git push
