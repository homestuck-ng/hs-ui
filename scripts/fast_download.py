#!/usr/bin/env python3
"""Download one pinned Samsung firmware through the same FUS path as samloader.

Several HTTP ranges run at once. Samsung accepts Range on this host, and a
single samloader stream is what makes Actions look stuck.
"""
import argparse
import hashlib
import os
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from Cryptodome.Cipher import AES

from samloader.fusclient import FUSClient
from samloader.main import initdownload
from samloader.request import binaryinform, getlogiccheck
from samloader.versionfetch import normalizevercode


def unpad(data):
    return data[:-data[-1]]


def xml_fields(text):
    root = ET.fromstring(text)
    found = {}
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "Data" and child.text:
                found[parent.tag] = child.text.strip()
    return found


def fus_inform(client, fw, model, region, imei):
    raw = client.makereq(
        "NF_DownloadBinaryInform.do",
        binaryinform(fw, model, region, imei, client.nonce),
    )
    return xml_fields(raw)


def auth_headers(client):
    authv = (
        'FUS nonce="' + client.encnonce + '", signature="' + client.auth
        + '", nc="", type="", realm="", newauth="1"'
    )
    return {
        "Authorization": authv,
        "User-Agent": "Kies2.0_FUS",
        "X-FUS-Protocol-Ver": "2.0",
    }


def fetch_range(url, params, headers, start, end, dest):
    hdrs = dict(headers)
    hdrs["Range"] = "bytes={}-{}".format(start, end)
    for attempt in range(4):
        try:
            with requests.get(url, params=params, headers=hdrs, stream=True, timeout=(30, 180)) as resp:
                if resp.status_code != 206:
                    raise RuntimeError("range {}-{} status {}".format(start, end, resp.status_code))
                with open(dest, "wb") as out:
                    for chunk in resp.iter_content(1024 * 1024):
                        if chunk:
                            out.write(chunk)
            got = os.path.getsize(dest)
            if got != end - start + 1:
                raise RuntimeError("range {}-{} short {}".format(start, end, got))
            return
        except Exception as exc:
            if attempt == 3:
                raise
            print("retry {}-{} ({})".format(start, end, exc), flush=True)
            time.sleep(2 + attempt)


def download_parallel(url, params, headers, size, dest, connections):
    connections = max(1, min(connections, 16))
    if connections == 1 or size < 8 * 1024 * 1024:
        download_single(url, params, headers, dest)
        return
    part_dir = dest + ".parts"
    os.makedirs(part_dir, exist_ok=True)
    spans = []
    chunk = size // connections
    for i in range(connections):
        start = i * chunk
        end = size - 1 if i == connections - 1 else (start + chunk - 1)
        spans.append((i, start, end, os.path.join(part_dir, "part{:02d}".format(i))))
    print("ranges {} x {} bytes".format(connections, size), flush=True)
    with ThreadPoolExecutor(max_workers=connections) as pool:
        futures = [
            pool.submit(fetch_range, url, params, headers, start, end, path)
            for _, start, end, path in spans
        ]
        for fut in as_completed(futures):
            fut.result()
    with open(dest, "wb") as out:
        for _, _, _, path in spans:
            with open(path, "rb") as inp:
                while True:
                    buf = inp.read(1024 * 1024)
                    if not buf:
                        break
                    out.write(buf)
            os.remove(path)
    os.rmdir(part_dir)


def download_single(url, params, headers, dest):
    print("single stream", flush=True)
    with requests.get(url, params=params, headers=headers, stream=True, timeout=(30, 180)) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as out:
            done = 0
            for chunk in resp.iter_content(1024 * 1024):
                if not chunk:
                    continue
                out.write(chunk)
                done += len(chunk)
                if done % (256 * 1024 * 1024) < len(chunk):
                    print("got {:.0f} MB".format(done / (1024 * 1024)), flush=True)


def decrypt_file(src, dest, key):
    size = os.path.getsize(src)
    if size % 16:
        raise SystemExit("encrypted size {} is not a 16-byte multiple".format(size))
    cipher = AES.new(key, AES.MODE_ECB)
    block = 1024 * 1024
    remaining = size
    with open(src, "rb") as inf, open(dest, "wb") as out:
        while remaining:
            take = min(block, remaining)
            data = inf.read(take)
            if len(data) != take:
                raise SystemExit("short read while decrypting")
            remaining -= take
            plain = cipher.decrypt(data)
            out.write(unpad(plain) if remaining == 0 else plain)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--imei", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--connections", type=int, default=8)
    args = parser.parse_args()

    version = normalizevercode(args.version)
    pda = version.split("/")[0]
    os.makedirs(args.out_dir, exist_ok=True)
    client = FUSClient()
    info = fus_inform(client, version, args.model, args.region, args.imei)
    got = info.get("LATEST_FW_VERSION") or ""
    filename = info.get("BINARY_NAME") or ""
    path = info.get("MODEL_PATH") or ""
    ap_name = info.get("DEVICE_PDA_CODE1_FILE") or ""
    print("offered {} ap {}".format(got, ap_name or filename), flush=True)
    if not got.startswith(pda + "/") and pda not in ap_name:
        raise SystemExit(
            "FUS does not have {}. It offered {}.".format(pda, got.split("/")[0] or ap_name)
        )
    size = int(info["BINARY_BYTE_SIZE"])
    logic = info.get("LOGIC_VALUE_FACTORY") or info.get("LOGIC_VALUE_HOME")
    if not logic:
        raise SystemExit("FUS reply has no decryption value")
    key = hashlib.md5(getlogiccheck(got, logic).encode()).digest()
    initdownload(client, filename)
    headers = auth_headers(client)
    url = "http://cloud-neofussvr.samsungmobile.com/NF_DownloadBinaryForMass.do"
    params = "file=" + path + filename
    enc = os.path.join(args.out_dir, filename)
    try:
        download_parallel(url, params, headers, size, enc, args.connections)
    except Exception as exc:
        print("parallel download failed ({}); falling back to one stream".format(exc), flush=True)
        if os.path.exists(enc):
            os.remove(enc)
        download_single(url, params, headers, enc)
    got = os.path.getsize(enc)
    if got != size:
        raise SystemExit("downloaded {} of {} bytes".format(got, size))
    decrypted = enc.replace(".enc4", "").replace(".enc2", "")
    if decrypted == enc:
        decrypted = enc + ".zip"
    print("decrypt", flush=True)
    decrypt_file(enc, decrypted, key)
    os.remove(enc)
    print("zip", decrypted, flush=True)


if __name__ == "__main__":
    main()
