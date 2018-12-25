#!/bin/bash

set -ex

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP="$(mktemp -d)"

cleanup() {
	if [[ -d $TEMP ]]; then
		rm -rf -- "$TEMP"
	fi
}

trap cleanup EXIT

pushd "$TEMP"

mkdir pwb_env
touch pwb_env/user-config.py

mkdir images
pushd images
PYWIKIBOT_DIR=../pwb_env python3 /data/project/shared/pywikipedia/core/pwb.py "$DIR"/arcomArchive.py > ../export.xml
popd

"$DIR"/sort export.xml export-sorted.xml

ARCHIVE_TIMESTAMP=$(date +%Y%m%d)
tar -cvJf commonsarchivewiki-$ARCHIVE_TIMESTAMP-images.tar.xz -C images .
xz -zc export-sorted.xml > commonsarchivewiki-$ARCHIVE_TIMESTAMP-history.xml.xz

COLLECTION=opensource
IDENTIFIER=wiki-commonsarchive
ia upload $IDENTIFIER commonsarchivewiki-$ARCHIVE_TIMESTAMP-images.tar.xz commonsarchivewiki-$ARCHIVE_TIMESTAMP-history.xml.xz --metadata=mediatype:web --metadata=collection:$COLLECTION
ia metadata $IDENTIFIER --modify="Last-updated-date:REMOVE_TAG" --modify="Last-update-date:$(date +%Y-%m-%d)"
