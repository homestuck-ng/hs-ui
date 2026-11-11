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

mkdir -p "$DEST"
echo "samloader download $MODEL $CSC $VER4 -> $DEST"
args=(-m "$MODEL" -r "$CSC" -i "$IMEI")
if [[ -n "$SERIAL" ]]; then
    args+=(-s "$SERIAL")
fi
args+=(download -v "$VER4" -O "$DEST")
samloader "${args[@]}"

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
echo "downloaded $PDA"
