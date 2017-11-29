#!/bin/sh

set -e

bump_version() {
    FILE="${1:?}"
    PATTERN="${2:?}"
    cp "$FILE" /tmp/version
    sed "s/$PATTERN/\1$VERSION\3/" /tmp/version > "$FILE"
    git add "$FILE"
}

FEATURE=${FEATURE:?}
VERSION=${VERSION:?}

# Merge feature (abort if there are no changes)
git checkout master
git fetch
git merge
git merge --no-ff --no-commit $FEATURE
[ -f .git/MERGE_HEAD ]

# Bump version
bump_version doc/conf.py "^\(version = release = '\)\(.*\)\('\)$"

# Run checks
make check

# Publish
git commit
git tag $VERSION
git push origin master $VERSION

# Clean up
git branch -d $FEATURE
git push --delete origin $FEATURE
