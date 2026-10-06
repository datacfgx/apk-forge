#!/usr/bin/env bash
# REPLICAR_apk.sh — bancada APK sem root: apktool + apksigner + zipalign + JRE (Debian).
# Mesmo padrao do REPLICAR_kali_tools.sh: apt-cache resolve, apt-get download, dpkg-deb -x.
# /mnt tem limite de 100MiB POR ARQUIVO -> tar vazado em partes de 90m.
# Uso:
#   bash REPLICAR_apk.sh          # resolve, baixa, extrai em /tmp/apkroot, grava partes em /mnt
#   bash REPLICAR_apk.sh untar    # restaura /tmp/apkroot das partes (segundos, por turno)
set -u
KROOT=/tmp/apkroot
STATE=/tmp/aptstate_apk
TAR=/mnt/agents/output/apkroot.tar.gz

if [ "${1:-}" = "untar" ]; then
  ls "$TAR"-part-* >/dev/null 2>&1 || { echo "partes ausentes: $TAR-part-*"; exit 1; }
  rm -rf "$KROOT"; mkdir -p "$KROOT"
  cat "$TAR"-part-* | tar xz -C /tmp
  echo "ok: $KROOT"; exit 0
fi

mkdir -p "$KROOT" "$STATE/lists/partial" /tmp/debs_apk
apt-get -o Dir::State="$STATE" -o Dir::Cache="$STATE/cache" update >/dev/null 2>&1 || true

python3 - "$STATE" > /tmp/pkglist_apk.txt <<'PY'
import subprocess, re, sys
state = sys.argv[1]
seeds = ["apktool", "apksigner", "zipalign"]
seen, out = set(), []
for s in seeds:
    r = subprocess.run(["apt-cache", "-o", "Dir::State=" + state, "depends", "--recurse",
                        "--no-recommends", "--no-suggests", "--no-conflicts",
                        "--no-breaks", "--no-replaces", "--no-enhances", s],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        m = re.match(r"\s+(?:PreDepends|Depends):\s+(\S+)", line)
        cand = m.group(1) if m else (line.strip() if (line and line[0] not in " |") else None)
        if cand and not cand.startswith("<") and cand not in seen:
            seen.add(cand); out.append(cand)
print("\n".join(out))
PY

cd /tmp/debs_apk
while read -r p; do
  [ -n "$p" ] || continue
  apt-get -o Dir::State="$STATE" download "$p" >/dev/null 2>&1 || echo "falhou: $p"
done < /tmp/pkglist_apk.txt
rm -rf "$KROOT"; mkdir -p "$KROOT"
for d in /tmp/debs_apk/*.deb; do
  [ -e "$d" ] && dpkg-deb -x "$d" "$KROOT" 2>/dev/null
done
rm -f "$TAR"-part-*
(cd /tmp && tar czf - apkroot | split -b 90m - "$TAR"-part-)
echo "pronto: $(ls "$TAR"-part-* | wc -l) partes"
