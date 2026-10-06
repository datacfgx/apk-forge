#!/usr/bin/env python3
# apk_forge.py — canivete de APK / APK swiss knife: info, abrir, extrair, remontar, assinar
# stdlib pura (python >= 3.8). AXML decode em python puro.
import argparse, datetime, glob, hashlib, os, re, shutil, ssl, struct, subprocess, sys, zipfile

VERSAO = "1.0"

# ----------------------------- AXML decoder (python puro) -----------------------------
RES_STRING_POOL_TYPE = 0x0001
RES_XML_TYPE = 0x0003
RES_XML_RESOURCE_MAP_TYPE = 0x0180
RES_XML_START_NAMESPACE_TYPE = 0x0100
RES_XML_END_NAMESPACE_TYPE = 0x0101
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103
RES_XML_CDATA_TYPE = 0x0104
TYPE_STRING = 0x03
TYPE_ATTRIBUTE = 0x02
TYPE_REFERENCE = 0x01
TYPE_FLOAT = 0x04
TYPE_DIMENSION = 0x05
TYPE_FRACTION = 0x06
TYPE_FIRST_INT = 0x10
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_INT_BOOLEAN = 0x12
TYPE_FIRST_COLOR_INT = 0x1C
TYPE_LAST_COLOR_INT = 0x1F
TYPE_LAST_INT = 0x1F


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class AXML:
    def __init__(self, data):
        self.data = data
        self.strings = []
        self.resmap = []
        self.events = []

    def _string(self, idx):
        if 0 <= idx < len(self.strings):
            return self.strings[idx]
        return ""

    def parse_string_pool(self, off):
        b = self.data
        _tipo, _hs, size = _u16(b, off), _u16(b, off + 2), _u32(b, off + 4)
        scount, scount8, flags = _u32(b, off + 8), _u32(b, off + 12), _u32(b, off + 16)
        sstart = _u32(b, off + 20)
        utf8 = bool(flags & 0x100)
        offs = [_u32(b, off + 28 + 4 * i) for i in range(scount)]
        base = off + sstart
        out = []
        for so in offs:
            p = base + so
            if utf8:
                # utf8: 2 length fields (chars, bytes) encoded len
                _ = b[p]; p += 1
                if b[p - 1] & 0x80:
                    p += 1
                blen = b[p]; p += 1
                if blen & 0x80:
                    blen = ((blen & 0x7F) << 8) | b[p]; p += 1
                out.append(b[p:p + blen].decode("utf-8", "replace"))
            else:
                # utf16
                ln = _u16(b, p); p += 2
                if ln & 0x8000:
                    ln = ((ln & 0x7FFF) << 16) | _u16(b, p); p += 2
                out.append(b[p:p + ln * 2].decode("utf-16-le", "replace"))
        self.strings = out
        return size

    def parse(self):
        b = self.data
        if len(b) < 8 or _u16(b, 0) != RES_XML_TYPE:
            raise ValueError("nao e um AXML binario (cabecalho invalido)")
        total = _u32(b, 4)
        off = 8
        while off < total:
            ctype = _u16(b, off)
            csize = _u32(b, off + 4)
            if ctype == RES_STRING_POOL_TYPE:
                self.parse_string_pool(off)
            elif ctype == RES_XML_RESOURCE_MAP_TYPE:
                n = (csize - 8) // 4
                self.resmap = [_u32(b, off + 8 + 4 * i) for i in range(n)]
            elif ctype == RES_XML_START_ELEMENT_TYPE:
                ns = _u32(b, off + 16)
                name = _u32(b, off + 20)
                attr_start = _u16(b, off + 24)
                attr_size = _u16(b, off + 26)
                attr_count = _u16(b, off + 28)
                attrs = []
                abase = off + 16 + attr_start  # attrExt comeca apos node header (8+8)
                for i in range(attr_count):
                    ao = abase + i * attr_size
                    a_ns = _u32(b, ao)
                    a_name = _u32(b, ao + 4)
                    a_raw = _u32(b, ao + 8)
                    a_type = b[ao + 15]
                    a_data = _u32(b, ao + 16)
                    attrs.append((a_ns, a_name, a_raw, a_type, a_data))
                self.events.append(("start", ns, name, attrs))
            elif ctype == RES_XML_END_ELEMENT_TYPE:
                ns = _u32(b, off + 16)
                name = _u32(b, off + 20)
                self.events.append(("end", ns, name))
            elif ctype == RES_XML_CDATA_TYPE:
                data_idx = _u32(b, off + 16)
                self.events.append(("text", data_idx))
            off += csize
        return self

    def val_str(self, raw, atype, adata):
        if raw != 0xFFFFFFFF:
            return self._string(raw)
        if atype == TYPE_STRING:
            return self._string(adata)
        if atype == TYPE_INT_BOOLEAN:
            return "true" if adata else "false"
        if TYPE_FIRST_INT <= atype <= TYPE_LAST_INT:
            if TYPE_FIRST_COLOR_INT <= atype <= TYPE_LAST_COLOR_INT:
                return "#%08X" % adata
            return str(adata if atype == TYPE_INT_DEC else adata)
        if atype == TYPE_REFERENCE:
            return "@%08X" % adata
        if atype in (TYPE_ATTRIBUTE,):
            return "?%08X" % adata
        return "0x%08X" % adata

    def to_xml(self):
        esc = {"<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;"}
        def e(s):
            return "".join(esc.get(c, c) for c in s)
        out = ['<?xml version="1.0" encoding="utf-8"?>']
        stack = []
        for ev in self.events:
            if ev[0] == "start":
                _, ns, name, attrs = ev
                n = self._string(name)
                attr_txt = ""
                for (a_ns, a_name, a_raw, a_type, a_data) in attrs:
                    an = self._string(a_name)
                    av = self.val_str(a_raw, a_type, a_data)
                    attr_txt += ' %s="%s"' % (e(an), e(av))
                out.append("%s<%s%s>" % ("  " * len(stack), e(n), attr_txt))
                stack.append(n)
            elif ev[0] == "end":
                if stack:
                    stack.pop()
                out.append("%s</%s>" % ("  " * len(stack), e(self._string(ev[2]))))
            elif ev[0] == "text":
                out.append("  " * len(stack) + e(self._string(ev[1])))
        return "\n".join(out) + "\n"


def decode_axml(data):
    return AXML(data).parse().to_xml()


def manifest_info(xml_txt):
    info = {}
    m = re.search(r"<manifest[^>]*", xml_txt)
    if m:
        tag = m.group(0)
        for chave in ("package", "versionCode", "versionName", "platformBuildVersionCode"):
            mm = re.search(chave + r'="([^"]*)"', tag)
            if mm:
                info[chave] = mm.group(1)
    us = re.findall(r"<uses-sdk[^>]*", xml_txt)
    if us:
        mm = re.search(r'minSdkVersion="([^"]*)"', us[0])
        if mm:
            info["minSdk"] = mm.group(1)
        mm = re.search(r'targetSdkVersion="([^"]*)"', us[0])
        if mm:
            info["targetSdk"] = mm.group(1)
    info["permissoes"] = re.findall(r"<uses-permission[^>]*android:name=\"([^\"]*)\"", xml_txt)
    app = re.search(r"<application[^>]*", xml_txt)
    if app:
        mm = re.search(r'android:label="([^"]*)"', app.group(0))
        if mm:
            info["label"] = mm.group(1)
        info["debuggable"] = "android:debuggable=\"true\"" in app.group(0)
    return info

# ----------------------------- helpers de APK -----------------------------

def abre_apk(apk):
    if not os.path.isfile(apk):
        erro("apk nao encontrado: %s" % apk)
    return zipfile.ZipFile(apk)


def erro(msg):
    print("ERRO: " + msg)
    sys.exit(1)


def sha256_arq(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def dex_strings(data, minlen=4):
    ascii_s = re.findall(rb"[\x20-\x7e]{%d,}" % minlen, data)
    wide_s = re.findall(rb"(?:[\x20-\x7e]\x00){%d,}" % minlen, data)
    out = set()
    for s in ascii_s:
        out.add(s.decode("ascii", "replace"))
    for s in wide_s:
        out.add(s.decode("utf-16-le", "replace"))
    return sorted(out)


def cert_fingerprint(zf):
    # extrai cert de META-INF/*.RSA|DSA|EC via openssl (stdlib nao parseia PKCS#7)
    cand = [n for n in zf.namelist()
            if n.upper().startswith("META-INF/") and n.upper().endswith((".RSA", ".DSA", ".EC"))]
    if not cand:
        return None, "sem bloco de assinatura (APK nao assinado)"
    openssl = shutil.which("openssl")
    if not openssl:
        return None, "openssl ausente no PATH"
    with zf.open(cand[0]) as f:
        der = f.read()
    p7 = subprocess.run([openssl, "pkcs7", "-inform", "DER", "-print_certs", "-outform", "PEM"],
                        input=der, capture_output=True)
    if p7.returncode != 0:
        return None, "pkcs7 falhou: %s" % p7.stderr.decode()[:200]
    pem = p7.stdout.decode()
    m = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem, re.S)
    if not m:
        return None, "nenhum certificado no bloco"
    cert_pem = m.group(0)
    tmp = "/tmp/_apk_forge_cert.pem"
    open(tmp, "w").write(cert_pem)
    try:
        dec = ssl._ssl._test_decode_cert(tmp)
        der2 = ssl.PEM_cert_to_DER_cert(cert_pem)
        fp256 = hashlib.sha256(der2).hexdigest()
        fp1 = hashlib.sha1(der2).hexdigest()
        subj = ", ".join("=".join(t) for t in dec.get("subject", ()))
        emissor = ", ".join("=".join(t) for t in dec.get("issuer", ()))
        return {"sha256": fp256, "sha1": fp1, "subject": subj, "issuer": emissor,
                "validade": dec.get("notAfter", "?")}, None
    except Exception as e:
        return None, "decode do cert falhou: %s" % e
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ----------------------------- subcomandos -----------------------------

def cmd_info(apk, _resto):
    zf = abre_apk(apk)
    nomes = zf.namelist()
    dexs = [n for n in nomes if n.endswith(".dex")]
    print("apk      : %s" % apk)
    print("sha256   : %s" % sha256_arq(apk))
    print("entries  : %d | dex: %d" % (len(nomes), len(dexs)))
    man = None
    if "AndroidManifest.xml" in nomes:
        try:
            with zf.open("AndroidManifest.xml") as f:
                man = decode_axml(f.read())
        except Exception as e:
            print("manifest : decode falhou: %s" % e)
    if man:
        info = manifest_info(man)
        for k in ("package", "versionCode", "versionName", "label", "minSdk", "targetSdk"):
            if k in info:
                print("%-10s: %s" % (k, info[k]))
        print("debuggable: %s" % info.get("debuggable", False))
        if info.get("permissoes"):
            print("permissoes (%d):" % len(info["permissoes"]))
            for p in info["permissoes"]:
                print("  - %s" % p)
    cert, err = cert_fingerprint(zf)
    if cert:
        print("cert sha256: %s" % cert["sha256"])
        print("cert sha1  : %s" % cert["sha1"])
        print("cert sujeito: %s" % cert["subject"])
        print("cert validade: %s" % cert["validade"])
    else:
        print("cert     : %s" % err)
    zf.close()
    return 0


def cmd_abrir(apk, resto):
    dest = resto[0] if resto else os.path.splitext(os.path.basename(apk))[0]
    if os.path.exists(dest):
        erro("destino ja existe: %s" % dest)
    zf = abre_apk(apk)
    zf.extractall(dest)
    zf.close()
    # decode do manifest + strings do dex, lado a lado
    man_bin = os.path.join(dest, "AndroidManifest.xml")
    if os.path.isfile(man_bin):
        try:
            data = open(man_bin, "rb").read()
            xml = decode_axml(data)
            open(os.path.join(dest, "AndroidManifest.decoded.xml"), "w").write(xml)
            print("manifest decodificado -> AndroidManifest.decoded.xml")
        except Exception as e:
            print("manifest decode falhou: %s" % e)
    for dex in glob.glob(os.path.join(dest, "*.dex")) + glob.glob(os.path.join(dest, "assets", "*.dex")):
        try:
            strs = dex_strings(open(dex, "rb").read())
            saida = dex + ".strings.txt"
            open(saida, "w").write("\n".join(strs) + "\n")
            print("strings: %s (%d)" % (os.path.basename(saida), len(strs)))
        except Exception as e:
            print("strings de %s falhou: %s" % (dex, e))
    print("aberto em: %s/" % dest)
    return 0


def cmd_extrair(apk, resto):
    if not resto:
        erro("uso: extrair <apk> <padrao> [destino] — ex: extrair app.apk 'res/*.xml' ./res")
    padrao = resto[0]
    dest = resto[1] if len(resto) > 1 else "."
    zf = abre_apk(apk)
    hits = [n for n in zf.namelist() if glob.fnmatch.fnmatch(n, padrao)]
    if not hits:
        zf.close()
        erro("nenhuma entry casa com: %s" % padrao)
    for n in hits:
        zf.extract(n, dest)
        print("extraido: %s" % n)
    zf.close()
    return 0


def cmd_remontar(dire, resto):
    if not os.path.isdir(dire):
        erro("diretorio nao existe: %s" % dire)
    saida = resto[0] if resto else dire.rstrip("/") + ".remontado.apk"
    nomes = []
    for raiz, _dirs, arqs in os.walk(dire):
        for a in arqs:
            cam = os.path.join(raiz, a)
            nomes.append(os.path.relpath(cam, dire))
    nomes.sort()
    # alinha primeiro: dex e manifest no inicio (convencao android)
    nomes.sort(key=lambda n: (0 if (n.endswith(".dex") or n == "AndroidManifest.xml") else 1, n))
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for n in nomes:
            z.write(os.path.join(dire, n), n)
    print("remontado: %s (%d entries, %d bytes)" % (saida, len(nomes), os.path.getsize(saida)))
    print("ATENCAO: APK nao assinado. Rode: apk_forge.py assinar %s" % saida)
    return 0


def cmd_assinar(apk, resto):
    if not os.path.isfile(apk):
        erro("apk nao encontrado: %s" % apk)
    apksigner = shutil.which("apksigner")
    if not apksigner:
        erro("apksigner ausente. instale build-tools (REPLICAR_apk.sh) ou: apt install apksigner")
    ks = None
    for cand in (os.path.expanduser("~/.android/debug.keystore"),):
        if os.path.isfile(cand):
            ks = cand
    if "--keystore" in resto:
        ks = resto[resto.index("--keystore") + 1]
    if not ks:
        erro("nenhum keystore. gere: keytool -genkey -v -keystore ~/.android/debug.keystore "
             "-storepass android -alias androiddebugkey -keypass android -dname 'CN=Android Debug'")
    saida = apk.replace(".apk", ".assinado.apk")
    r = subprocess.run([apksigner, "sign", "--ks", ks, "--ks-pass", "pass:android",
                        "--key-pass", "pass:android", "--out", saida, apk],
                       capture_output=True, text=True)
    if r.returncode != 0:
        erro("apksigner falhou: %s" % (r.stderr or r.stdout)[:400])
    v = subprocess.run([apksigner, "verify", "--print-certs", saida],
                       capture_output=True, text=True)
    print("assinado: %s" % saida)
    print(v.stdout[:600])
    return 0


def cmd_ajuda(_apk, _resto):
    print("""apk-forge v%s — canivete de APK
uso: apk_forge.py <comando> <apk|dir> [args]
  info <apk>                    ficha: manifest, cert, dex, hashes
  abrir <apk> [dir]             extrai tudo + manifest decodificado + strings do dex
  extrair <apk> <glob> [dest]   extrai so entries casando o padrao
  remontar <dir> [saida.apk]    reempacota dir em APK (alinhado, sem assinar)
  assinar <apk> [--keystore K]  apksigner sign + verify
  menu                          menu interativo
AXML decode em python puro; turbo apktool/apksigner quando presente no PATH.
""" % VERSAO)
    return 0


ACOES = {"info": cmd_info, "abrir": cmd_abrir, "extrair": cmd_extrair,
         "remontar": cmd_remontar, "assinar": cmd_assinar}


def menu():
    while True:
        print("""
== apk-forge v%s ==
 1) info      2) abrir      3) extrair
 4) remontar  5) assinar    0) sair
""" % VERSAO)
        try:
            op = input("escolha> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if op == "0":
            return 0
        acao = {"1": "info", "2": "abrir", "3": "extrair", "4": "remontar", "5": "assinar"}.get(op)
        if not acao:
            print("opcao invalida.")
            continue
        alvo = input("apk/dir> ").strip()
        if not alvo:
            continue
        try:
            ACOES[acao](alvo, [])
        except SystemExit:
            pass
        except Exception as e:
            print("falhou: %s" % e)


def main(argv):
    if not argv or argv[0] == "menu":
        return menu()
    comando = argv[0]
    if comando in ("ajuda", "-h", "--help", "help"):
        return cmd_ajuda(None, [])
    if comando not in ACOES:
        print("comando desconhecido: %s" % comando)
        cmd_ajuda(None, [])
        return 2
    if len(argv) < 2:
        print("uso: apk_forge.py %s <apk|dir> [args]" % comando)
        return 2
    try:
        return ACOES[comando](argv[1], argv[2:])
    except SystemExit as e:
        return e.code or 0
    except zipfile.BadZipFile:
        print("ERRO: arquivo nao e um ZIP/APK valido")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
