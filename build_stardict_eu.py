import bz2
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
import nltk

XML_PATH = Path("euwiktionary.xml.bz2")
OUT_DIR = Path("eu-eu-hiztegia")
DICT_BASE = "eu-eu-hiztegia"

FOREIGN_LANG_CODES = {
    "es", "en", "fr", "de", "la", "it", "pt", "ca", "gl", "oc", "eo", "ja",
    "zh", "ru", "ar", "el", "nl", "sv", "pl", "fi", "hu", "tr", "he", "hi",
    "ko", "br", "cy", "ga", "gd", "ast", "an", "ro", "cs", "da", "no", "uk",
}

FOREIGN_LANG_NAMES = {
    "gaztelania", "frantsesa", "ingelesa", "latina", "alemana", "italiera",
    "katalana", "galiziera", "portugesa", "esperantoa", "japoniera", "txinera",
    "errusiera", "arabiera", "greziera", "nederlandera", "suediera", "poloniera",
}

SKIP_TEMPLATES = {
    "ahoskera", "itzulpenak", "itzul", "erreferentziak", "kanpo-loturak",
    "deklinabide", "deklinabidea", "aditz", "aditza", "izen", "izena", "iz",
    "ad", "izond", "adb", "hizkuntza", "wikipedia", "commons", "aurkibidea",
}

POS_MAP = {
    "izena": "iz.", "izen": "iz.", "-iz-": "iz.",
    "aditza": "ad.", "aditz": "ad.", "-ad-": "ad.",
    "izenondoa": "izond.", "izond": "izond.", "-izond-": "izond.",
    "adberbioa": "adb.", "adb": "adb.", "-adb-": "adb.",
    "izenordaina": "izord.", "izord": "izord.",
    "lokuzioa": "lok.", "lok": "lok.", "esapidea": "esap.",
}

WN_POS_MAP = {"n": "iz.", "v": "ad.", "a": "izond.", "s": "izond.", "r": "adb."}

# Formas conjugadas frecuentes (aditz trinkoak y auxiliares) -> lema
IRREGULAR_VERBS = {
    "izan": [
        "naiz", "haiz", "da", "gara", "zara", "zarete", "dira",
        "nintzen", "hintzen", "zen", "ginen", "zinen", "zineten", "ziren",
        "nintzateke", "litzateke", "ginateke", "lirateke", "zaio", "zaie", "zitzaion",
    ],
    "ukan": [
        "dut", "duzu", "du", "dugu", "duzue", "dute", "ditut", "ditu", "ditugu", "dituzte",
        "nuen", "zenuen", "zuen", "genuen", "zenuten", "zuten", "nituen", "zituen", "zituzten",
        "diot", "dio", "die", "zien", "zidan", "zigun",
    ],
    "egon": [
        "nago", "hago", "dago", "gaude", "zaude", "zaudete", "daude",
        "nengoen", "zegoen", "geunden", "zeunden", "zeuden",
    ],
    "ibili": [
        "nabil", "habil", "dabil", "gabiltza", "zabiltza", "dabiltza",
        "nenbilen", "zebilen", "genbiltzan", "zebiltzan",
    ],
    "etorri": [
        "nator", "hator", "dator", "gatoz", "zatoz", "datoz",
        "nentorren", "zetorren", "gentozen", "zetozen",
    ],
    "joan": [
        "noa", "hoa", "doa", "goaz", "zoaz", "doaz",
        "nindoan", "zihoan", "ginhoazen", "zihoazen",
    ],
    "eduki": [
        "daukat", "daukazu", "dauka", "daukagu", "daukate", "dauzkat", "dauzka", "dauzkate",
        "neukan", "zeukan", "geneukan", "zeukaten", "neuzkan", "zeuzkan",
    ],
    "jakin": [
        "dakit", "dakizu", "daki", "dakigu", "dakite", "dakizkit", "dakizki",
        "nekien", "zekien", "genekien", "zekiten",
    ],
    "esan": [
        "diot", "diozu", "dio", "diogu", "diote", "nioen", "zioen", "genioen", "zioten",
    ],
    "eraman": [
        "daramat", "darama", "daramagu", "daramate", "neraman", "zeraman", "zeramaten",
    ],
    "ekarri": [
        "dakart", "dakar", "dakargu", "dakarte", "nekarren", "zekarren", "zekarten",
    ],
}


def eval_template(match: re.Match) -> str:
    content = match.group(1).strip()
    parts = [p.strip() for p in content.split("|")]
    name = parts[0].lower()
    args = [a for a in parts[1:] if a and "=" not in a and a != "eu"]
    if name in SKIP_TEMPLATES or name.startswith("-"):
        return ""
    if name in ("sinonimo", "sinonimoak", "sin") and args:
        return f"(Sin.: {', '.join(args)})"
    if name in ("antonimo", "antonimoak", "ant") and args:
        return f"(Ant.: {', '.join(args)})"
    if not args and len(name) <= 12:
        return f"<i>[{name}]</i>"
    if args:
        return f"<i>({', '.join(args)})</i>"
    return ""


def clean_wikitext(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^/>]*/\s*>", "", text)
    text = re.sub(r"\[\[(?:Kategoria|Fitxategi|Irudi|File|Image|Category):[^\]]+\]\]", "", text, flags=re.I)
    for _ in range(3):
        text = re.sub(r"\{\{([^{}]+)\}\}", eval_template, text)
    text = re.sub(r"\{\{.*?\}\}", "", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'''([^']+)'''", r"<b>\1</b>", text)
    text = re.sub(r"''([^']+)''", r"<i>\1</i>", text)
    return re.sub(r"\s+", " ", text).strip()


def is_language_header(line: str):
    s = line.strip().lower()
    m_dash = re.match(r"^\{\{-([a-z\-]+)-\}\}$", s)
    if m_dash:
        code = m_dash.group(1)
        if code in ("eu", "euskara"):
            return "eu"
        if code in FOREIGN_LANG_CODES:
            return "foreign"
        return None
    m_hizk = re.search(r"\{\{\s*hizkuntza\s*\|\s*([a-z]{2,3})\s*\}\}", s)
    if m_hizk:
        return "eu" if m_hizk.group(1) == "eu" else "foreign"
    m_h2 = re.match(r"^==\s*([^=]+?)\s*==$", s)
    if m_h2:
        hdr = re.sub(r"[\{\}\[\]\|]", " ", m_h2.group(1)).strip()
        if "euskara" in hdr or hdr == "eu":
            return "eu"
        if hdr in FOREIGN_LANG_CODES or any(fl in hdr for fl in FOREIGN_LANG_NAMES):
            return "foreign"
    return None


def extract_eu_section(raw_text: str) -> str:
    lines = raw_text.splitlines()
    has_any_lang_hdr = False
    current_lang = None
    eu_lines = []
    for line in lines:
        ltype = is_language_header(line)
        if ltype is not None:
            has_any_lang_hdr = True
            current_lang = ltype
            continue
        if current_lang == "eu":
            eu_lines.append(line)
    if eu_lines:
        return "\n".join(eu_lines)
    if not has_any_lang_hdr:
        if re.search(r"\[\[\s*Kategoria\s*:\s*Euskar", raw_text, re.I) or not re.search(
            r"\[\[\s*Kategoria\s*:\s*(?:Gaztelania|Frantses|Ingeles|Latin|Aleman|Italiera|Katalan)", raw_text, re.I
        ):
            return raw_text
    return ""


def load_euskal_wordnet(entries: dict):
    print("2/5 Descargando y procesando Euskal WordNet (UPV/EHU - IXA)...")
    nltk.download("wordnet", quiet=True)
    nltk.download("omw-2.0", quiet=True)
    from nltk.corpus import wordnet as wn

    wn_senses = defaultdict(list)
    for syn in wn.all_synsets():
        eu_lemmas = [l.replace("_", " ").strip() for l in syn.lemma_names("eus")]
        if not eu_lemmas:
            continue

        pos_label = WN_POS_MAP.get(syn.pos(), "")
        es_lemmas = [l.replace("_", " ").strip() for l in syn.lemma_names("spa")]

        # Hiperónimos en euskera (definición categorial en euskera)
        hyper_eu = []
        for h in syn.hypernyms():
            for hl in h.lemma_names("eus"):
                hl_clean = hl.replace("_", " ").strip()
                if hl_clean not in hyper_eu:
                    hyper_eu.append(hl_clean)

        # Hipónimos o términos relacionados en euskera
        rel_eu = []
        for r in syn.similar_tos() + syn.also_sees() + syn.verb_groups() + syn.hyponyms()[:4]:
            for rl in r.lemma_names("eus"):
                rl_clean = rl.replace("_", " ").strip()
                if rl_clean not in rel_eu:
                    rel_eu.append(rl_clean)

        for w in eu_lemmas:
            syns_eu = [x for x in eu_lemmas if x.lower() != w.lower()]
            parts = []
            if syns_eu:
                parts.append(f"<b>Sin.:</b> {', '.join(syns_eu[:8])}")
            if hyper_eu:
                parts.append(f"<b>Mota:</b> {', '.join([x for x in hyper_eu if x.lower() != w.lower()][:5])}")
            if not syns_eu and rel_eu:
                parts.append(f"<b>Erl.:</b> {', '.join([x for x in rel_eu if x.lower() != w.lower()][:5])}")
            if es_lemmas:
                parts.append(f"<i>[es: {', '.join(es_lemmas[:5])}]</i>")

            if parts:
                line = (f"<i>({pos_label})</i> " if pos_label else "") + " · ".join(parts)
                if line not in wn_senses[w]:
                    wn_senses[w].append(line)

    added_new = 0
    for w, lines in wn_senses.items():
        numbered = [f"{idx}. {text}" for idx, text in enumerate(lines[:10], 1)]
        block = f"<b>{w}</b> <small><i>[Euskal WordNet - EHU]</i></small><br>" + "<br>".join(numbered)
        if w not in entries:
            added_new += 1
        entries[w].append(block)

    print(f"    -> {len(wn_senses)} lemas en Euskal WordNet ({added_new} lemas nuevos añadidos a Wikiztegia).")


def add_declensions(stem: str, ends_in_vowel: bool, forms: set):
    if ends_in_vowel:
        suffixes = (
            "a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin",
            "arentzat", "entzat", "agaz", "akaz", "az", "ez", "an", "etan",
            "tik", "etatik", "ra", "etara", "raino", "etaraino", "rantz",
            "etarantz", "ko", "etako", "rik", "ok",
        )
    else:
        suffixes = (
            "a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin",
            "arentzat", "entzat", "agaz", "akaz", "ez", "ean", "etan",
            "etik", "etatik", "era", "etara", "eraino", "etaraino", "erantz",
            "etarantz", "eko", "etako", "ik", "ok",
        )
    for s in suffixes:
        forms.add(stem + s)

    rel_bases = (stem + "ko", stem + "etako") if ends_in_vowel else (stem + "eko", stem + "etako")
    for rbase in rel_bases:
        for rs in (
            "a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin",
            "arentzat", "entzat", "an", "etan", "tik", "etatik", "ra", "etara", "z", "ez",
        ):
            forms.add(rbase + rs)


def generate_eu_inflections(word: str) -> set:
    w = word.lower().strip()
    if " " in w or len(w) < 2 or not w.isalpha():
        return set()

    forms = set()
    vowels = set("aeiou")

    if w.endswith("a"):
        add_declensions(w[:-1], True, forms)
        add_declensions(w, True, forms)
    elif w.endswith("r"):
        add_declensions(w, False, forms)
        add_declensions(w + "r", False, forms)
    elif w[-1] in vowels:
        add_declensions(w, True, forms)
    else:
        add_declensions(w, False, forms)

    for deg in ("ago", "egi"):
        forms.add(w + deg)
        forms.add(w + deg + "a")
        forms.add(w + deg + "ak")

    verb_stems = []
    if (w.endswith("tu") or w.endswith("du")) and len(w) >= 4:
        verb_stems.append((w[:-2], ["tzen", "tuko", "duko", "tzea", "tzeko", "tuta", "turik", "tutako", "turiko"]))
    elif w.endswith("i") and len(w) >= 3:
        verb_stems.append((w[:-1], ["tzen", "ten", "iko", "tzea", "tea", "tzeko", "teko", "ita", "irik", "itako", "iriko"]))
    elif w.endswith("n") and len(w) >= 3:
        verb_stems.append((w[:-1], ["ten", "tzen", "ngo", "ko", "tea", "teko", "nda", "nik", "ndako", "niko"]))

    for vstem, vsuffixes in verb_stems:
        for vs in vsuffixes:
            vform = vstem + vs
            forms.add(vform)
            if vform.endswith(("tzea", "tea")):
                nbase = vform[:-1]
                for ns in ("k", "ri", "ren", "rekin", "gatik", "n", "tik", "ra", "ko"):
                    forms.add(nbase + ns)
            elif vform.endswith(("tzeko", "teko", "tako", "riko")):
                for rs in ("a", "ak", "ek", "ari", "ei", "aren", "en", "an", "etan"):
                    forms.add(vform + rs)

    forms.discard(w)
    forms.discard(word)
    return forms


def stardict_sort_key(word: str):
    b = word.encode("utf-8")
    ascii_lower = bytes(c + 32 if 65 <= c <= 90 else c for c in b)
    return (ascii_lower, b)


def local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def main():
    print("1/5 Extrayendo entradas en euskera desde Wikiztegia...")
    entries = defaultdict(list)
    redirects = {}

    with bz2.open(XML_PATH, "rb") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            tname = local_tag(elem.tag)
            if tname == "siteinfo":
                elem.clear()
                continue
            if tname != "page":
                continue

            title, ns, raw_text = "", "", ""
            for child in elem.iter():
                ctag = local_tag(child.tag)
                if ctag == "title" and child.text:
                    title = child.text.strip()
                elif ctag == "ns" and child.text:
                    ns = child.text.strip()
                elif ctag == "text" and child.text:
                    raw_text = child.text

            elem.clear()

            if ns != "0" or not title or ":" in title or not raw_text:
                continue

            m_red = re.match(r"^\s*#(?:REDIRECT|BIRZUZENDU)\s*\[\[([^\]]+)\]\]", raw_text, re.I)
            if m_red:
                target = m_red.group(1).split("|")[0].strip()
                if target and target != title:
                    redirects[title] = target
                continue

            eu_text = extract_eu_section(raw_text)
            if not eu_text:
                continue

            current_pos = ""
            defs = []
            lines = eu_text.splitlines()
            for i, line in enumerate(lines):
                line_s = line.strip()
                if line_s.startswith("===") or re.match(r"^\{\{-[a-z]+-\}\}$", line_s.lower()):
                    hdr_clean = line_s.lower()
                    for k, v in POS_MAP.items():
                        if k in hdr_clean:
                            current_pos = v
                            break
                    continue

                if re.match(r"^#(?![*:])", line_s):
                    gloss_raw = re.sub(r"^#+\s*", "", line_s)
                    gloss = clean_wikitext(gloss_raw)
                    if not gloss or len(gloss) < 2:
                        continue

                    ex_str = ""
                    if i + 1 < len(lines) and re.match(r"^#[:*]", lines[i + 1].strip()):
                        ex_raw = re.sub(r"^#[:*]+\s*", "", lines[i + 1].strip())
                        ex_clean = clean_wikitext(ex_raw)
                        if ex_clean:
                            ex_str = f" <br><small><i>Adib.: «{ex_clean}»</i></small>"

                    pos_tag = f"<i>({current_pos})</i> " if current_pos else ""
                    defs.append(f"{len(defs) + 1}. {pos_tag}{gloss}{ex_str}")

            if defs:
                block = f"<b>{title}</b> <small><i>[Wikiztegia]</i></small><br>" + "<br>".join(defs)
                entries[title].append(block)

    print(f"    -> {len(entries)} lemas extraídos de Wikiztegia.")

    # Añadir Euskal WordNet (UPV/EHU)
    load_euskal_wordnet(entries)
    print(f"    -> Total combinado: {len(entries)} lemas en euskera.")

    print("3/5 Generando declinaciones, conjugaciones y aditz trinkoak (.syn)...")
    sorted_words = sorted(entries.keys(), key=stardict_sort_key)
    word_to_idx = {w: idx for idx, w in enumerate(sorted_words)}

    syn_pairs = set()
    for w, idx in word_to_idx.items():
        if w.lower() != w and w.lower() not in word_to_idx:
            syn_pairs.add((w.lower(), idx))
        for inf in generate_eu_inflections(w):
            if inf not in word_to_idx:
                syn_pairs.add((inf, idx))

    for lemma, conj_list in IRREGULAR_VERBS.items():
        if lemma in word_to_idx:
            target_idx = word_to_idx[lemma]
            for conj in conj_list:
                if conj not in word_to_idx:
                    syn_pairs.add((conj, target_idx))
                    syn_pairs.add((conj + "la", target_idx))
                    syn_pairs.add((conj + "n", target_idx))

    for src, dst in redirects.items():
        if dst in word_to_idx and src not in word_to_idx:
            syn_pairs.add((src, word_to_idx[dst]))

    sorted_syns = sorted(syn_pairs, key=lambda item: (stardict_sort_key(item[0]), item[1]))
    print(f"    -> {len(sorted_syns)} formas flexionadas indexadas.")

    print("4/5 Escribiendo archivos binarios StarDict...")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dict_path = OUT_DIR / f"{DICT_BASE}.dict"
    idx_path = OUT_DIR / f"{DICT_BASE}.idx"
    syn_path = OUT_DIR / f"{DICT_BASE}.syn"
    ifo_path = OUT_DIR / f"{DICT_BASE}.ifo"

    offset = 0
    with dict_path.open("wb") as f_dict, idx_path.open("wb") as f_idx:
        for w in sorted_words:
            html_def = "<br><br>".join(entries[w])
            def_bytes = html_def.encode("utf-8")
            w_bytes = w.encode("utf-8")

            f_dict.write(def_bytes)
            f_idx.write(w_bytes + b"\x00" + struct.pack(">II", offset, len(def_bytes)))
            offset += len(def_bytes)

    with syn_path.open("wb") as f_syn:
        for syn_w, target_idx in sorted_syns:
            f_syn.write(syn_w.encode("utf-8") + b"\x00" + struct.pack(">I", target_idx))

    idx_size = idx_path.stat().st_size
    ifo_content = (
        "StarDict's dict ifo file\n"
        "version=2.4.2\n"
        f"wordcount={len(sorted_words)}\n"
        f"synwordcount={len(sorted_syns)}\n"
        f"idxfilesize={idx_size}\n"
        "bookname=Euskara Hiztegia (Wikiztegia + EHU)\n"
        "sametypesequence=h\n"
    )
    ifo_path.write_text(ifo_content, encoding="utf-8")

    if shutil.which("dictzip"):
        subprocess.run(["dictzip", "-f", str(dict_path)], check=True)

    print("5/5 Verificando palabras de prueba (hondatzeko, sendikoek, hezia):")
    syn_map = defaultdict(list)
    for syn_w, idx in sorted_syns:
        syn_map[syn_w].append(sorted_words[idx])

    for test_w in ("hondatu", "hondatzeko", "sendi", "sendikoek", "hezi", "hezia"):
        in_main = test_w in word_to_idx
        in_syn = syn_map.get(test_w, [])
        print(f"    - {test_w:12s} -> lema directo: {in_main} | redirige a: {in_syn}")


if __name__ == "__main__":
    main()
