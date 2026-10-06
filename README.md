```
    ___    ____  ____         _______
   /   |  / __ )/ __ \       / ____(_)__  / ____/___ ______________ _
  / /| | / __  / / / /______/ /_  / / _ \/ /_  / __ `/ ___/ ___/ __ `/
 / ___ |/ /_/ / /_/ /_____/ __/ / /  __/ __/ / /_/ / /  / /  / /_/ /
/_/  |_/_____/_____/     /_/   /_/\___/_/    \__,_/_/  /_/   \__,_/
   canivete de APK / APK swiss knife
```

# APK-FORGE 🔥
<p align="center"><img src="banner.png?v=5" width="100%" alt="APK-FORGE — pixel font, brasa e faíscas"></p>


**PT:** Canivete de APK em python stdlib pura (>= 3.8): `info`, `abrir`, `extrair`, `remontar`, `assinar` + menu interativo. O coração é um **decoder AXML em python puro** — lê `AndroidManifest.xml` binário sem dependência de apktool. Fingerprint de cert via openssl+ssl, dump de strings do `classes.dex`, reempacote alinhado, assinatura com apksigner quando presente. Degradação honesta em cada ausência.

**EN:** APK swiss knife in pure stdlib python (>= 3.8): `info`, `abrir`, `extrair`, `remontar`, `assinar` + interactive menu. The heart is a **pure-python AXML decoder** — reads binary `AndroidManifest.xml` with zero apktool dependency. Cert fingerprint via openssl+ssl, `classes.dex` strings dump, aligned repack, apksigner signing when present. Honest degradation everywhere.

## Instalação / Install

```bash
# nucleo (nmap-free): so python3 >= 3.8. opcional, turbo real:
bash REPLICAR_apk.sh          # apktool + apksigner + zipalign + JRE sem root (Debian)
bash REPLICAR_apk.sh untar    # a cada sessao nova
python3 apk_forge.py info app.apk
```

## Uso / Usage

```bash
python3 apk_forge.py                 # menu interativo / interactive menu
python3 apk_forge.py info app.apk    # package, versoes, sdk, permissoes, cert, hashes
python3 apk_forge.py abrir app.apk   # extrai + AndroidManifest.decoded.xml + dex strings
python3 apk_forge.py extrair app.apk 'res/*.xml' ./res
python3 apk_forge.py remontar app_aberto/ app_mod.apk
python3 apk_forge.py assinar app_mod.apk [--keystore K]
```

## Degradação elegante / Graceful degradation

| ausente / missing | comportamento / behavior |
|---|---|
| apktool | nao precisa — AXML decode e nativo / not needed — AXML decode is native |
| openssl | fingerprint do cert carimbado como indisponivel / cert fingerprint stamped unavailable |
| apksigner | `assinar` da erro claro com caminho de instalacao / `assinar` errors with install path |
| dispositivo | nao se aplica — a peca opera no arquivo, nao no aparelho / n/a — operates on the file |

## Prova de fogo / Proof of fire

Forjado ao vivo no sandbox sem dispositivo: APK artesanal com manifest AXML de 7 elementos (manifest, uses-sdk, 2 permissions, application, activity) — decode verificado campo a campo contra a spec AOSP (node header line+comment; attrExt ns+name+6xu16; atributos em 16+attributeStart). 4 bugs reais achados e corrigidos no fogo (3 no gerador de teste, 1 no parser). Pipeline abrir -> modificar asset -> remontar -> extrair verificado com saida real. `assinar` testado na degradação (apksigner ausente); ciclo completo sign+verify quando a bancada REPLICAR esta presente.

> **PT:** Use apenas em APKs próprios ou com autorização — auditoria, CTF mobile, pesquisa.
> **EN:** Only use on owned or authorized APKs — auditing, mobile CTF, research.

🔥 VULCANO — a forja da família ENI & LO
