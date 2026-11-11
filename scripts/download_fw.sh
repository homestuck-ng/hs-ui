#!/usr/bin/env bash
# Download one pinned firmware the way UN1CA sixteen does:
#   samloader -m MODEL -r CSC -i IMEI [-s SERIAL] download -O DIR
# from https://github.com/ananjaser1211/samloader
# -v is set so FUS is asked for this PDA, not the latest XXV build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/target/r0q/config.sh"

FW="${1:?firmware PDA/CSC/CP}"
DEST="${2:?output directory}"

PDA="${FW%%/*}"
BIT="${PDA: -5:1}"
case "$BIT" in
    [0-9]|A|B|C) ;;
    *)
        echo "refusing $PDA: bootloader bit $BIT is above C" >&2
        exit 1
        ;;
esac

# Anan's samloader wants four fields: PDA/CSC/MODEM/PDA.
VER4="$FW"
if [[ "$(awk -F/ '{print NF}' <<< "$FW")" == "3" ]]; then
    VER4="$FW/$PDA"
fi

IMEI="${SAMSUNG_IMEI:-$IMEI_DEFAULT}"
SERIAL="${SAMSUNG_SERIAL:-}"
CONNECTIONS="${FW_CONNECTIONS:-8}"
CACHE="$ROOT/work/firmware-cache/$PDA"

mkdir -p "$DEST"
shopt -s nullglob
cached=("$CACHE"/AP_*.tar.md5 "$CACHE"/AP_*.tar)
if ((${#cached[@]})); then
    echo "cache hit $PDA"
    cp -a "${cached[@]}" "$DEST/"
    echo "downloaded $PDA"
    exit 0
fi

# FUS no longer returns these old PDAs. The exact AP tars are stored on the
# firmware-v1 release, split under GitHub's 2GB asset limit.
RELEASE_BASE="${FW_RELEASE_BASE:-https://github.com/homestuck-ng/hs-ui/releases/download/firmware-v1}"
man="$DEST/${PDA}.txt"
if curl -fsSL --retry 3 "$RELEASE_BASE/${PDA}.txt" -o "$man"; then
    name="$(awk -F= '$1=="name"{print $2}' "$man")"
    sha="$(awk -F= '$1=="sha256"{print $2}' "$man")"
    parts="$(awk -F= '$1=="parts"{print $2}' "$man")"
    out="$DEST/$name"
    : > "$out"
    echo "release $PDA ($parts parts)"
    for ((i = 0; i < parts; i++)); do
        part="$(printf '%s.part%02d' "$PDA" "$i")"
        echo "get $part"
        curl -fL --retry 5 --retry-all-errors -o "$DEST/$part" "$RELEASE_BASE/$part"
        cat "$DEST/$part" >> "$out"
        rm -f "$DEST/$part"
    done
    echo "$sha  $out" | sha256sum -c -
    rm -f "$man"
    echo "downloaded $PDA"
    exit 0
fi
rm -f "$man"

echo "fus download $MODEL $CSC $VER4 -> $DEST ($CONNECTIONS connections)"
python3 -u "$ROOT/scripts/fast_download.py" \
    --model "$MODEL" \
    --region "$CSC" \
    --version "$VER4" \
    --imei "$IMEI" \
    --out-dir "$DEST" \
    --connections "$CONNECTIONS"

shopt -s nullglob
enc=("$DEST"/*.enc4 "$DEST"/*.enc2)
if ((${#enc[@]})); then
    echo "samloader left an encrypted file; decrypt did not finish" >&2
    printf '%s\n' "${enc[@]}" >&2
    exit 1
fi
zips=("$DEST"/*.zip)
if ((${#zips[@]} != 1)); then
    echo "expected one decrypted zip in $DEST" >&2
    printf '%s\n' "${zips[@]-}" >&2
    exit 1
fi

AP="$(unzip -Z1 "${zips[0]}" | awk '/(^|\/)AP_/{print; exit}')"
if [[ "$AP" != *"_${PDA}_"* && "$AP" != "AP_${PDA}"* ]]; then
    echo "AP inside the zip is $AP, wanted PDA $PDA" >&2
    exit 1
fi
echo "AP $AP"
unzip -o -j "${zips[0]}" "$AP" -d "$DEST"
# BL and CP stay in the zip and are deleted with it. They are not unpacked.
rm -f "${zips[0]}"
ap_file="$(find "$DEST" -maxdepth 1 \( -name 'AP_*.tar.md5' -o -name 'AP_*.tar' \) | head -n 1)"
limit=$((9 * 1000 * 1000 * 1000))
ap_size="$(stat -c%s "$ap_file")"
used=0
if [[ -d "$ROOT/work/firmware-cache" ]]; then
    used="$(du -sb "$ROOT/work/firmware-cache" | awk '{print $1}')"
fi
if (( ap_size + used < limit )); then
    mkdir -p "$CACHE"
    cp -a "$ap_file" "$CACHE/"
    echo "cached $PDA"
else
    echo "not caching $PDA, Actions cache limit is 10GB"
fi
echo "downloaded $PDA"
