"""Synthetic Turkish IT support requests with intent + NER labels.

Templates are filled with entity values so character spans are exact. Variants
add typos, missing diacritics, abbreviations and Turkish/English mixing. With
--llm, an LLM paraphrases a share of the samples; entity strings must survive
verbatim or the paraphrase is dropped (spans are re-located by string search).

    python ml/data/generate.py --n 3000 --out ml/data/raw.jsonl [--llm 0.3]
"""

import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import write_jsonl

VALUES = {
    "YAZILIM": ["Outlook", "Teams", "Excel", "Word", "VPN", "GlobalProtect", "SAP", "Chrome",
                "Adobe Reader", "Photoshop", "OneDrive", "Zoom", "SharePoint", "AutoCAD",
                "Visual Studio", "Office"],
    "CIHAZ": ["laptop", "bilgisayar", "yazıcı", "monitör", "klavye", "mouse", "telefon",
              "dock", "kulaklık", "kamera", "tablet"],
    "HATA_KODU": ["0x800CCC0E", "0x80070005", "0x0000011b", "0x80070643", "809", "691",
                  "ERR_CERT_AUTHORITY_INVALID", "0x8004010F"],
    "DEPARTMAN": ["Muhasebe", "Finans", "İnsan Kaynakları", "Satış", "Pazarlama", "Hukuk",
                  "Operasyon", "Satın Alma", "Müşteri Hizmetleri"],
    "KISI": ["Ayşe Yılmaz", "Mehmet Kaya", "Zeynep Demir", "Ahmet Şahin", "Elif Çelik",
             "Burak Aydın", "Selin Öztürk", "Can Arslan"],
    "IP_ADRESI": ["10.0.0.15", "192.168.1.20", "172.16.4.8", "10.10.2.33"],
    "TARIH": ["dün", "bugün", "bu sabah", "dün akşam", "geçen hafta", "12.11.2026",
              "3 Kasım", "pazartesi"],
}

# {SLOT} placeholders are entity slots; plain text otherwise.
TEMPLATES: dict[str, list[str]] = {
    "password_reset": [
        "Şifremi unuttum, sıfırlayabilir misiniz?",
        "{TARIH} şifremin süresi doldu, yenisini nasıl alırım",
        "{YAZILIM} şifremi sıfırlamam lazım",
        "Parolamı değiştirmek istiyorum, {DEPARTMAN} departmanındayım",
        "{KISI} için şifre sıfırlama talebi",
    ],
    "account_locked": [
        "Hesabım kilitlendi giriş yapamıyorum",
        "{TARIH} birkaç kez yanlış şifre girdim, hesabım kilitli",
        "{YAZILIM} hesabım kilitlenmiş",
        "{KISI} hesabı kilitlendi, açabilir misiniz",
    ],
    "vpn_issue": [
        "VPN bağlanmıyor",
        "Evden VPN'e bağlanamıyorum, {HATA_KODU} hatası alıyorum",
        "{YAZILIM} sürekli kopuyor, {TARIH} başladı",
        "VPN hata {HATA_KODU} veriyor",
        "GlobalProtect bağlanıyor ama hiçbir sisteme erişemiyorum",
    ],
    "email_issue": [
        "{YAZILIM} açılmıyor {HATA_KODU} hatası veriyor",
        "Mail gönderemiyorum, giden kutusunda kalıyor",
        "Posta kutum doldu e-posta alamıyorum",
        "{TARIH} itibarıyla Outlook e-postaları senkronize etmiyor",
        "{KISI} adlı kişiye mail gitmiyor",
    ],
    "software_install": [
        "{YAZILIM} kurulumu yapmam gerekiyor",
        "{CIHAZ} için {YAZILIM} yüklemek istiyorum",
        "{YAZILIM} lisansı lazım, {DEPARTMAN} ekibindeyim",
        "Kurulum {HATA_KODU} hatasıyla yarıda kalıyor",
        "Yeni {CIHAZ} geldi, {YAZILIM} kurar mısınız",
    ],
    "hardware_issue": [
        "{CIHAZ} açılmıyor",
        "{CIHAZ} görüntü vermiyor",
        "{TARIH} {CIHAZ} çalışmayı bıraktı",
        "{CIHAZ} çok ısınıyor ve kapanıyor",
        "{CIHAZ} tuşları basmıyor",
    ],
    "network_issue": [
        "İnternet yok",
        "Wi-Fi sürekli kopuyor",
        "{IP_ADRESI} adresine ping atamıyorum",
        "Ofiste ağ bağlantısı çok yavaş",
        "{TARIH} bu yana kablolu internet çalışmıyor, IP {IP_ADRESI}",
    ],
    "access_request": [
        "{DEPARTMAN} klasörüne erişim yetkisi istiyorum",
        "{YAZILIM} için yetki talebim var",
        "{KISI} için paylaşılan klasöre erişim açılması lazım",
        "Yeni başladım, {YAZILIM} erişimim yok",
    ],
    "printer_issue": [
        "Yazıcı kağıt sıkıştırıyor",
        "Yazıcıdan çıktı alamıyorum {HATA_KODU} hatası",
        "{DEPARTMAN} katındaki yazıcı çevrimdışı",
        "Yazıcı toneri bitti",
    ],
    "ticket_status": [
        "INC-{NUM} numaralı talebimin durumu ne?",
        "{TARIH} açtığım talep ne oldu",
        "Talebim hala çözülmedi, durumu nedir",
        "INC-{NUM} kapandı mı?",
        "{YAZILIM} için açtığım ticket ne aşamada",
        "Açık taleplerimi görebilir miyim",
        "{TARIH} bildirdiğim {CIHAZ} arızası ne durumda",
    ],
    "report_request": [
        "Bu hafta {DEPARTMAN} departmanından kaç ticket geldi?",
        "Geçen ay en çok hangi tür arıza bildirildi",
        "{DEPARTMAN} için açık talep sayısını raporla",
        "Bu ay kaç VPN ticket'ı açıldı",
        "Ortalama çözüm süresi kaç saat?",
        "{TARIH} kaç kritik ticket açıldı",
        "{DEPARTMAN} ekibinin en çok yaşadığı sorun ne",
        "Açık ticketların takımlara göre dağılımı",
        "Son 30 günde kaç {YAZILIM} talebi geldi",
        "Bu ay çözülen talep sayısı kaç",
    ],
    "other": [
        "Merhaba",
        "Teşekkürler",
        "Kahve makinesi bozuk",
        "Toplantı odası rezervasyonu nasıl yapılır",
        "Yemekhane menüsü ne",
        "Klima çok soğuk üflüyor",
        "Otopark kartım çalışmıyor",
        "Maaş bordrom ne zaman yatar",
        "Kargo geldi mi",
        "İyi çalışmalar",
        "{KISI} bugün ofiste mi",
        "Servis saatleri değişti mi",
    ],
}
PREFIXES = ["", "", "", "Merhaba, ", "Selam, ", "İyi günler, ", "Merhabalar ", "Acil: ",
            "Kolay gelsin, ", "Rica etsem ", "Günaydın, "]
SUFFIXES = ["", "", "", " yardımcı olur musunuz?", " lütfen yardım", " acil!", " teşekkürler.",
            " ne yapmalıyım?", " bakabilir misiniz", " sabahtan beri böyle", " çok acil",
            " işlerim aksıyor"]
JOINERS = [", ayrıca ", ". Bir de ", " ve ", ". Ek olarak "]
ABBREVIATIONS = {"bilgisayar": "pc", "şifre": "sifre", "lütfen": "lutfen",
                 "değil": "degil", "çalışmıyor": "calismiyor"}
ENGLISH = {"açılmıyor": "not working", "bağlanmıyor": "connect olmuyor",
           "kurulumu": "installation"}
DEASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def fill(template: str, rng: random.Random) -> tuple[str, list[dict]]:
    template = template.replace("{NUM}", str(rng.randint(10001, 10999)))
    text, entities, pos = "", [], 0
    for match in re.finditer(r"\{(\w+)\}", template):
        text += template[pos:match.start()]
        value = rng.choice(VALUES[match.group(1)])
        entities.append({"start": len(text), "end": len(text) + len(value),
                         "label": match.group(1)})
        text += value
        pos = match.end()
    return text + template[pos:], entities


def _replace_outside(text: str, entities: list[dict], fn) -> tuple[str, list[dict]]:
    """Apply `fn` to non-entity segments and shift spans accordingly."""
    out, new_ents, pos = "", [], 0
    for ent in sorted(entities, key=lambda e: e["start"]):
        out += fn(text[pos:ent["start"]])
        start = len(out)
        out += text[ent["start"]:ent["end"]]
        new_ents.append({**ent, "start": start, "end": len(out)})
        pos = ent["end"]
    return out + fn(text[pos:]), new_ents


def typo(segment: str, rng: random.Random) -> str:
    chars = list(segment)
    for _ in range(max(1, len(chars) // 25)):
        if len(chars) > 3:
            i = rng.randrange(len(chars) - 1)
            if chars[i].isalpha() and chars[i + 1].isalpha():
                chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def augment(text: str, entities: list[dict], rng: random.Random) -> tuple[str, list[dict]]:
    r = rng.random()
    if r < 0.15:
        return _replace_outside(text, entities, lambda s: s.translate(DEASCII))
    if r < 0.30:
        return _replace_outside(text, entities, lambda s: typo(s, rng))
    if r < 0.40:
        def abbreviate(s):
            for k, v in {**ABBREVIATIONS, **ENGLISH}.items():
                s = s.replace(k, v)
            return s
        return _replace_outside(text, entities, abbreviate)
    if r < 0.50:
        return _replace_outside(text, entities, str.lower)
    return text, entities


def sample(rng: random.Random, multi_ratio: float) -> dict:
    issue_intents = [i for i in TEMPLATES if i not in ("other", "report_request", "ticket_status")]
    if rng.random() < multi_ratio:
        first, second = rng.sample(issue_intents, 2)
        t1, e1 = fill(rng.choice(TEMPLATES[first]), rng)
        t2, e2 = fill(rng.choice(TEMPLATES[second]), rng)
        joiner = rng.choice(JOINERS)
        t2 = t2[0].lower() + t2[1:] if joiner.startswith((",", " ")) and \
            not any(e["start"] == 0 for e in e2) else t2
        offset = len(t1) + len(joiner)
        text = t1 + joiner + t2
        entities = e1 + [{**e, "start": e["start"] + offset, "end": e["end"] + offset} for e in e2]
        intents = [first, second]
    else:
        intent = rng.choice(list(TEMPLATES))
        text, entities = fill(rng.choice(TEMPLATES[intent]), rng)
        intents = [intent]
    prefix, suffix = rng.choice(PREFIXES), rng.choice(SUFFIXES)
    if prefix and not any(e["start"] == 0 for e in entities):
        text = text[0].lower() + text[1:]
    text = prefix + text + suffix
    entities = [{**e, "start": e["start"] + len(prefix), "end": e["end"] + len(prefix)}
                for e in entities]
    text, entities = augment(text, entities, rng)
    return {"text": text, "intents": intents, "entities": entities, "source": "template",
            "verified": False}


def llm_paraphrase(rows: list[dict], share: float, rng: random.Random) -> list[dict]:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.9)
    out = []
    for row in rows:
        if rng.random() >= share:
            out.append(row)
            continue
        values = [row["text"][e["start"]:e["end"]] for e in row["entities"]]
        prompt = ("Bu IT destek talebini bir şirket çalışanının yazacağı gibi farklı kelimelerle "
                  "yeniden yaz. Şu ifadeleri aynen koru: " + ", ".join(values or ["-"]) +
                  f"\n\nTalep: {row['text']}\nSadece yeni metni yaz.")
        text = str(llm.invoke(prompt).content).strip()
        entities, ok = [], True
        for ent, value in zip(row["entities"], values):
            idx = text.find(value)
            if idx < 0:
                ok = False
                break
            entities.append({**ent, "start": idx, "end": idx + len(value)})
        out.append({**row, "text": text, "entities": entities, "source": "llm"} if ok else row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--multi", type=float, default=0.2, help="share of multi-intent samples")
    parser.add_argument("--llm", type=float, default=0.0, help="share paraphrased by an LLM")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--out", default=str(Path(__file__).parent / "raw.jsonl"))
    args = parser.parse_args()
    rng = random.Random(args.seed)
    rows, seen = [], set()
    for _ in range(args.n * 20):
        row = sample(rng, args.multi)
        key = " ".join(row["text"].lower().split())
        if key not in seen:
            seen.add(key)
            rows.append(row)
        if len(rows) == args.n:
            break
    if args.llm > 0:
        rows = llm_paraphrase(rows, args.llm, rng)
    for i, row in enumerate(rows):
        row["id"] = f"s{i:05d}"
    write_jsonl(args.out, rows)
    print(f"wrote {len(rows)} samples -> {args.out}")


if __name__ == "__main__":
    main()
