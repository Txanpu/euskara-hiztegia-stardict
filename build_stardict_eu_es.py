import bz2
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
import nltk
from nltk.corpus import wordnet as wn

XML_PATH = Path("euwiktionary.xml.bz2")
OUT_DIR = Path("eu-es")
DICT_BASE = "eu-es"

WN_POS_MAP = {"n": "sust.", "v": "verbo", "a": "adj.", "s": "adj.", "r": "adv."}

IRREGULAR_VERBS = {
    "izan": ["naiz", "haiz", "da", "gara", "zara", "zarete", "dira", "nintzen", "hintzen", "zen", "ginen", "zinen", "zineten", "ziren", "zaio", "zaie", "zitzaion"],
    "ukan": ["dut", "duzu", "du", "dugu", "duzue", "dute", "ditut", "ditu", "ditugu", "dituzte", "nuen", "zenuen", "zuen", "genuen", "zenuten", "zuten", "nituen", "zituen", "zituzten", "diot", "dio", "die", "zien"],
    "egon": ["nago", "hago", "dago", "gaude", "zaude", "zaudete", "daude", "nengoen", "zegoen", "geunden", "zeunden", "zeuden"],
    "ibili": ["nabil", "habil", "dabil", "gabiltza", "zabiltza", "dabiltza", "nenbilen", "zebilen", "genbiltzan", "zebiltzan"],
    "etorri": ["nator", "hator", "dator", "gatoz", "zatoz", "datoz", "nentorren", "zetorren", "gentozen", "zetozen"],
    "joan": ["noa", "hoa", "doa", "goaz", "zoaz", "doaz", "nindoan", "zihoan", "ginhoazen", "zihoazen"],
    "eduki": ["daukat", "daukazu", "dauka", "daukagu", "daukate", "dauzkat", "dauzka", "dauzkate", "neukan", "zeukan", "geneukan", "zeukaten"],
    "jakin": ["dakit", "dakizu", "daki", "dakigu", "dakite", "nekien", "zekien", "genekien", "zekiten"],
    "esan": ["diot", "diozu", "dio", "diogu", "diote", "nioen", "zioen", "genioen", "zioten"],
    "eraman": ["daramat", "darama", "daramagu", "daramate", "neraman", "zeraman", "zeramaten"],
    "ekarri": ["dakart", "dakar", "dakargu", "dakarte", "nekarren", "zekarren", "zekarten"],
}


def add_declensions(stem: str, ends_in_vowel: bool, forms: set):
    suffixes = (
        ("a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin", "arentzat", "entzat", "agaz", "akaz", "az", "ez", "an", "etan", "tik", "etatik", "ra", "etara", "raino", "etaraino", "rantz", "etarantz", "ko", "etako", "rik", "ok")
        if ends_in_vowel else
        ("a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin", "arentzat", "entzat", "agaz", "akaz", "ez", "ean", "etan", "etik", "etatik", "era", "etara", "eraino", "etaraino", "erantz", "etarantz", "eko", "etako", "ik", "ok")
    )
    for s in suffixes:
        forms.add(stem + s)
    rel_bases = (stem + "ko", stem + "etako") if ends_in_vowel else (stem + "eko", stem + "etako")
    for rbase in rel_bases:
        for rs in ("a", "ak", "ek", "ari", "ei", "aren", "en", "arekin", "ekin", "arentzat", "entzat", "an", "etan", "tik", "etatik", "ra", "etara", "z", "ez"):
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
        forms.update((w + deg, w + deg + "a", w + deg + "ak"))

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
    return (bytes(c + 32 if 65 <= c <= 90 else c for c in b), b)


def local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def main():
    nltk.download("wordnet", quiet=True)
    nltk.download("omw-2.0", quiet=True)

    entries = defaultdict(list)

    # 1. Traducciones directas de Wikiztegia ({{itzul|es|...}})
    with bz2.open(XML_PATH, "rb") as f:
        for _, elem in ET.iterparse(f, events=("end",)):
            if local_tag(elem.tag) != "page":
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

            es_hits = re.findall(r"\{\{\s*itzul\+?\s*\|\s*es\s*\|\s*([^|}]+)", raw_text, re.I)
            clean_es = []
            for h in es_hits:
                h_clean = re.sub(r"[\[\]\{\}']", "", h).strip()
                if h_clean and h_clean not in clean_es:
                    clean_es.append(h_clean)
            if clean_es:
                entries[title].append(f"<b>{', '.join(clean_es)}</b> <small><i>[Wikiztegia]</i></small>")

    # 2. Alineación Euskal WordNet (eus -> spa)
    for syn in wn.all_synsets():
        eu_lemmas = [l.replace("_", " ").strip() for l in syn.lemma_names("eus")]
        es_lemmas = [l.replace("_", " ").strip() for l in syn.lemma_names("spa")]
        if not eu_lemmas or not es_lemmas:
            continue
        pos = WN_POS_MAP.get(syn.pos(), "")
        hyper_es = []
        for h in syn.hypernyms():
            for hl in h.lemma_names("spa"):
                hl_c = hl.replace("_", " ").strip()
                if hl_c not in hyper_es:
                    hyper_es.append(hl_c)
        ctx = f" <i>({', '.join(hyper_es[:3])})</i>" if hyper_es else ""
        pos_tag = f"<i>[{pos}]</i> " if pos else ""
        line = f"{pos_tag}<b>{', '.join(es_lemmas[:6])}</b>{ctx}"
        for w in eu_lemmas:
            if line not in entries[w]:
                entries[w].append(line)

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
            t_idx = word_to_idx[lemma]
            for conj in conj_list:
                if conj not in word_to_idx:
                    syn_pairs.update({(conj, t_idx), (conj + "la", t_idx), (conj + "n", t_idx)})

    sorted_syns = sorted(syn_pairs, key=lambda item: (stardict_sort_key(item[0]), item[1]))

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
            numbered = [f"{i}. {d}" for i, d in enumerate(entries[w][:10], 1)]
            def_bytes = (f"<b>{w}</b><br>" + "<br>".join(numbered)).encode("utf-8")
            f_dict.write(def_bytes)
            f_idx.write(w.encode("utf-8") + b"\x00" + struct.pack(">II", offset, len(def_bytes)))
            offset += len(def_bytes)

    with syn_path.open("wb") as f_syn:
        for syn_w, t_idx in sorted_syns:
            f_syn.write(syn_w.encode("utf-8") + b"\x00" + struct.pack(">I", t_idx))

    ifo_content = (
        "StarDict's dict ifo file\n"
        "version=2.4.2\n"
        f"wordcount={len(sorted_words)}\n"
        f"synwordcount={len(sorted_syns)}\n"
        f"idxfilesize={idx_path.stat().st_size}\n"
        "bookname=Euskara - Gaztelania (eu-es)\n"
        "sametypesequence=h\n"
    )
    ifo_path.write_text(ifo_content, encoding="utf-8")
    if shutil.which("dictzip"):
        subprocess.run(["dictzip", "-f", str(dict_path)], check=True)
    print(f"Compilado eu-es: {len(sorted_words)} lemas y {len(sorted_syns)} flexiones.")


if __name__ == "__main__":
    main()
