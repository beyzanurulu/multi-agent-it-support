"""Synthetic Turkish IT support requests with intent + NER labels.

Templates are filled with entity values so character spans are exact. Variants
add typos, missing diacritics, abbreviations and Turkish/English mixing. With
--llm, an LLM paraphrases a share of the samples; entity strings must survive
verbatim or the paraphrase is dropped (spans are re-located by string search).

    python ml/data/generate.py --n 3000 --out ml/data/raw.jsonl [--llm 0.3]
"""

import argparse
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import write_jsonl

VALUES = {
    "YAZILIM": ["Outlook", "Teams", "Excel", "Word", "VPN", "GlobalProtect", "SAP", "Chrome",
                "Adobe Reader", "Photoshop", "OneDrive", "Zoom", "SharePoint", "AutoCAD",
                "Visual Studio", "Office", "Power BI", "Jira", "Slack", "Webex", "Acrobat",
                "Logo Tiger", "Netsis", "Edge", "Firefox", "AnyDesk", "Outlook Web"],
    "CIHAZ": ["laptop", "bilgisayar", "yazıcı", "monitör", "klavye", "mouse", "telefon",
              "dock", "kulaklık", "kamera", "tablet", "dizüstü", "masaüstü", "projektör",
              "tarayıcı cihazı", "docking station", "ikinci ekran", "web kamerası"],
    "HATA_KODU": ["0x800CCC0E", "0x80070005", "0x0000011b", "0x80070643", "809", "691",
                  "ERR_CERT_AUTHORITY_INVALID", "0x8004010F", "0x80004005", "0xC004F074",
                  "0x80070057", "800", "720", "ERR_CONNECTION_TIMED_OUT", "0x0000007E"],
    "DEPARTMAN": ["Muhasebe", "Finans", "İnsan Kaynakları", "Satış", "Pazarlama", "Hukuk",
                  "Operasyon", "Satın Alma", "Müşteri Hizmetleri", "Bilgi İşlem", "Lojistik",
                  "Üretim", "Kalite", "Ar-Ge", "İç Denetim"],
    "KISI": ["Ayşe Yılmaz", "Mehmet Kaya", "Zeynep Demir", "Ahmet Şahin", "Elif Çelik",
             "Burak Aydın", "Selin Öztürk", "Can Arslan", "Deniz Koç", "Ece Kurt",
             "Murat Polat", "Gamze Aksoy", "Okan Erdem", "Seda Güneş", "Tolga Avcı",
             "Hande Yalçın"],
    "IP_ADRESI": ["10.0.0.15", "192.168.1.20", "172.16.4.8", "10.10.2.33", "10.20.30.40",
                  "192.168.0.105", "172.31.255.2", "10.1.12.250"],
    "TARIH": ["dün", "bugün", "bu sabah", "dün akşam", "geçen hafta", "12.11.2026",
              "3 Kasım", "pazartesi", "dünden beri", "iki gündür", "sabahtan beri",
              "cuma günü", "1 Aralık", "05.01.2027", "geçen ay", "öğleden sonra"],
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
# Second round of templates (wider phrasing; the first set alone was only 71 sentences).
TEMPLATES["password_reset"] += [
    "Şifremi hatırlamıyorum, {YAZILIM} girişi yapamıyorum",
    "Parolamın süresi {TARIH} doldu, yenilemem gerek",
    "{YAZILIM} bana sürekli şifre değiştir diyor ama kabul etmiyor",
    "Yeni şifre belirledim ama {CIHAZ} eski şifreyi istiyor",
    "Şifre sıfırlama maili gelmiyor",
    "{KISI} şifresini unutmuş, yardımcı olabilir misiniz",
    "Domain şifremi değiştirmem lazım",
    "Self servis portalda şifre yenileme hata veriyor",
    "Geçici şifre verildi ama giriş yapamıyorum",
    "{YAZILIM} parolamı nasıl güncellerim",
    "Şifremi üç kere yanlış girdim, yenisini almak istiyorum",
    "{DEPARTMAN} biriminden yeni başladım, ilk şifremi nasıl alırım",
]
TEMPLATES["account_locked"] += [
    "Hesabım bloke oldu",
    "Kullanıcım kilitli görünüyor, {YAZILIM} açılmıyor",
    "{TARIH} hesabım askıya alınmış",
    "Giriş ekranında hesabınız kilitlendi uyarısı çıkıyor",
    "{CIHAZ} oturum açmama izin vermiyor, hesap kilitli diyor",
    "Hesabımın kilidini açar mısınız",
    "MFA onayını kaçırdım hesabım kilitlendi",
    "Ard arda yanlış deneme yüzünden hesabım donduruldu",
    "{KISI} adlı kullanıcının hesabı kilitlenmiş",
    "Sabah girerken hesap devre dışı uyarısı aldım",
    "{DEPARTMAN} ortak hesabı kilitlendi",
]
TEMPLATES["vpn_issue"] += [
    "Uzaktan çalışırken şirket ağına bağlanamıyorum",
    "VPN bağlantısı {TARIH} kopup duruyor",
    "VPN'e bağlanınca internetim gidiyor",
    "{YAZILIM} kimlik doğrulama hatası veriyor",
    "Evden sunuculara erişemiyorum, tünel kurulmuyor",
    "VPN istemcisi {HATA_KODU} koduyla duruyor",
    "Otelden şirket ağına giremiyorum",
    "VPN çok yavaş, dosyalar açılmıyor",
    "{CIHAZ} üzerinde VPN profili görünmüyor",
    "VPN sertifikası süresi dolmuş uyarısı alıyorum",
    "Bağlanıyor gibi yapıp sonra düşüyor, VPN",
]
TEMPLATES["email_issue"] += [
    "E-postalarım gelmiyor",
    "{YAZILIM} sürekli şifre soruyor",
    "Gönderdiğim mailler {HATA_KODU} hatasıyla geri dönüyor",
    "Takvim davetleri {YAZILIM} uygulamasında görünmüyor",
    "{CIHAZ} üzerinde mail senkronize olmuyor",
    "Posta kutum {TARIH} kotayı aştı diyor",
    "Ek dosya gönderemiyorum, boyut hatası veriyor",
    "Paylaşılan posta kutusundaki mailleri göremiyorum",
    "Outlook arama çalışmıyor",
    "Spam klasörüne düşen önemli mailler var",
    "İmzam maillerde görünmüyor",
]
TEMPLATES["software_install"] += [
    "{YAZILIM} programına ihtiyacım var, yükleyebilir misiniz",
    "Software Center'da {YAZILIM} çıkmıyor",
    "{YAZILIM} güncellemesi {HATA_KODU} hatası veriyor",
    "{CIHAZ} üzerine yazılım kurma yetkim yok",
    "{DEPARTMAN} için {YAZILIM} lisansı talep ediyorum",
    "Eski {YAZILIM} sürümünü kaldırıp yenisini kurmak istiyorum",
    "Kurulum yarıda kalıyor, ne yapmalıyım",
    "{YAZILIM} eklentisi yüklenmiyor",
    "Yeni projeye başladım, {YAZILIM} lazım",
    "{TARIH} itibarıyla {YAZILIM} lisansım bitmiş",
]
TEMPLATES["hardware_issue"] += [
    "{CIHAZ} şarj olmuyor",
    "{CIHAZ} çok yavaş çalışıyor",
    "{CIHAZ} ses vermiyor",
    "{CIHAZ} kendi kendine yeniden başlıyor",
    "{CIHAZ} mavi ekran veriyor, {HATA_KODU}",
    "{CIHAZ} ekranında çizgiler var",
    "Yeni {CIHAZ} talep etmek istiyorum, mevcut olan bozuk",
    "{CIHAZ} fanı çok ses yapıyor",
    "{CIHAZ} USB girişleri çalışmıyor",
    "{KISI} için {CIHAZ} arızalı",
    "{CIHAZ} kırıldı, değişim lazım",
]
TEMPLATES["network_issue"] += [
    "Kablosuz ağ görünmüyor",
    "Ethernet takılı ama bağlantı yok",
    "İnternet sayfaları çok geç açılıyor",
    "{IP_ADRESI} adresli sunucuya erişemiyorum",
    "Ağda IP çakışması uyarısı alıyorum, {IP_ADRESI}",
    "{DEPARTMAN} katında Wi-Fi çekmiyor",
    "Misafir ağına bağlanılmıyor",
    "Tarayıcı {HATA_KODU} hatası veriyor, hiçbir site açılmıyor",
    "{TARIH} ağ paylaşımlarına ulaşamıyorum",
    "Ofis interneti kesik kesik geliyor",
    "Toplantı odasında ağ bağlantısı yok",
]
TEMPLATES["access_request"] += [
    "{YAZILIM} uygulamasında admin yetkisi lazım",
    "{DEPARTMAN} ortak klasörünü göremiyorum, izin verir misiniz",
    "Yeni ekip arkadaşım {KISI} için {YAZILIM} hesabı açılması lazım",
    "{YAZILIM} raporlarına erişimim kapanmış",
    "Proje klasörüne yazma iznine ihtiyacım var",
    "{YAZILIM} için okuma yetkisi talep ediyorum",
    "{TARIH} işe başlayan stajyere erişim tanımlanmalı",
    "Ayrılan çalışanın dosyalarına erişim istiyorum",
    "{DEPARTMAN} SharePoint sitesine ekler misiniz",
    "Sunucuya uzak masaüstü erişimi istiyorum, {IP_ADRESI}",
    "{YAZILIM} modülünde yetkim yetersiz diyor",
]
TEMPLATES["printer_issue"] += [
    "Yazıcı sürekli kağıt sıkıştı diyor",
    "Çıktılar soluk ve çizgili geliyor",
    "{DEPARTMAN} yazıcısı listede görünmüyor",
    "Renkli çıktı alamıyorum",
    "Yazıcı sırada bekliyor ama yazdırmıyor",
    "Tarayıcıdan taranan belgeler maile gelmiyor",
    "Yazıcı sürücüsü yüklenmiyor {HATA_KODU}",
    "{CIHAZ} üzerinden yazıcıya bağlanamıyorum",
    "Kartlı yazdırma çalışmıyor",
    "Yazıcı toner değiştir uyarısı veriyor ama yeni toner takılı",
    "Çift taraflı çıktı alamıyorum",
]
TEMPLATES["ticket_status"] += [
    "Bildirdiğim arıza çözüldü mü",
    "INC-{NUM} için bir gelişme var mı",
    "Açık taleplerimin listesini görebilir miyim",
    "{TARIH} açtığım kaydın son durumu ne",
    "Talebim hangi ekipte bekliyor",
    "INC-{NUM} neden hala açık",
]
TEMPLATES["report_request"] += [
    "Geçen hafta kaç ticket kapatıldı",
    "{DEPARTMAN} biriminin bu ayki talep sayısı",
    "Hangi ekipte en çok bekleyen ticket var",
    "Kritik önceliğe sahip açık talepleri listele",
    "Bu ay en çok arıza bildiren departman hangisi",
    "{YAZILIM} ile ilgili kaç talep açıldı",
]
TEMPLATES["other"] += [
    "Mutfaktaki buzdolabı soğutmuyor",
    "İzin talebimi nereden girerim",
    "Ofise kargo nereye bırakılıyor",
    "Toplantı salonunun kliması çalışmıyor",
    "Servis aracı kaçta kalkıyor",
    "Merhaba, iyi günler",
    "Görüşürüz, teşekkürler",
]
TEMPLATE_IDS = {intent: [f"{intent}:{i}" for i in range(len(t))] for intent, t in TEMPLATES.items()}

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
        i1, i2 = rng.randrange(len(TEMPLATES[first])), rng.randrange(len(TEMPLATES[second]))
        t1, e1 = fill(TEMPLATES[first][i1], rng)
        t2, e2 = fill(TEMPLATES[second][i2], rng)
        templates = [f"{first}:{i1}", f"{second}:{i2}"]
        joiner = rng.choice(JOINERS)
        t2 = t2[0].lower() + t2[1:] if joiner.startswith((",", " ")) and \
            not any(e["start"] == 0 for e in e2) else t2
        offset = len(t1) + len(joiner)
        text = t1 + joiner + t2
        entities = e1 + [{**e, "start": e["start"] + offset, "end": e["end"] + offset} for e in e2]
        intents = [first, second]
    else:
        intent = rng.choice(list(TEMPLATES))
        idx = rng.randrange(len(TEMPLATES[intent]))
        text, entities = fill(TEMPLATES[intent][idx], rng)
        intents = [intent]
        templates = [f"{intent}:{idx}"]
    prefix, suffix = rng.choice(PREFIXES), rng.choice(SUFFIXES)
    if prefix and not any(e["start"] == 0 for e in entities):
        text = text[0].lower() + text[1:]
    text = prefix + text + suffix
    entities = [{**e, "start": e["start"] + len(prefix), "end": e["end"] + len(prefix)}
                for e in entities]
    text, entities = augment(text, entities, rng)
    return {"text": text, "intents": intents, "entities": entities, "templates": templates,
            "source": "template", "verified": False}


def make_llm(provider: str, model: str | None):
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model or "qwen2.5:7b", temperature=0.9,
                          base_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model or "gpt-4o-mini", temperature=0.9)


def llm_paraphrase(rows: list[dict], share: float, rng: random.Random, llm) -> list[dict]:
    """Paraphrase a share of the rows; entity strings must survive or the row is kept as is."""
    out, done = [], 0
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
        done += 1
        if done % 100 == 0:
            print(f"  paraphrased {done}", file=sys.stderr)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--multi", type=float, default=0.2, help="share of multi-intent samples")
    parser.add_argument("--llm", type=float, default=0.0, help="share paraphrased by an LLM")
    parser.add_argument("--provider", choices=["openai", "ollama"], default="openai")
    parser.add_argument("--model", default=None, help="LLM model name for --llm")
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
        rows = llm_paraphrase(rows, args.llm, rng, make_llm(args.provider, args.model))
    for i, row in enumerate(rows):
        row["id"] = f"s{i:05d}"
    write_jsonl(args.out, rows)
    print(f"wrote {len(rows)} samples -> {args.out}")


if __name__ == "__main__":
    main()
