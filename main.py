from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures
import threading
import time
import os
import re
import json
from curl_cffi import requests as tls_requests
from google import genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEDARIKCILER = {
    # --- PERAKENDE SİTELER ---
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".ems-prd, .productItem, .product-item, .showcase"}
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-wrapper"}
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": "div[data-toggle='product'], .showcase"}
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box, .showcase"}
    },
    "Direnç.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": "div[data-toggle='product'], .showcase"}
    },
    "Kartal Otomasyon": {
        "url_sablonu": "https://www.kartalotomasyon.com.tr/arama/{}",
        "base_url": "https://www.kartalotomasyon.com.tr",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, div[data-toggle='product'], .product-item"}
    },

    # --- TOPTAN SİTELER ---
    "Özdisan": {
        "url_sablonu": "https://www.ozdisan.com/c?search={}",
        "base_url": "https://www.ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": "ozdisan_ozel"}
    },
    "Karaköy Elektronik": {
        "url_sablonu": "https://www.karakoyelektronik.com/arama/{}",
        "base_url": "https://www.karakoyelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item"}
    },
    "F1 Depo": {
        "url_sablonu": "https://www.f1depo.com/arama/{}",
        "base_url": "https://www.f1depo.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item"}
    },
    "Elektrovadi": {
        "url_sablonu": "https://www.elektrovadi.com/arama/{}",
        "base_url": "https://www.elektrovadi.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item"}
    },
    "Merter Elektronik": {
        "url_sablonu": "https://www.merterelektronik.com/Arama.aspx?kelime={}",
        "base_url": "https://www.merterelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".productItem, .showcase"}
    }
}

GIZLI_ISARETLERI = {"d-none", "hidden", "invisible", "display-none", "hide"}

TR_HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Cookie": 'NEXT_LOCALE=tr; user-settings=%7B%22languageCode%22%3A%22tr%22%2C%22currencyCode%22%3A%22TRY%22%2C%22countryCode%22%3A%22TR%22%2C%22isAuthenticated%22%3Afalse%7D; Currency=TRY; Language=tr'
}

USD_KUR = 34.50
EUR_KUR = 37.50
KUR_KAYNAK = "Varsayılan"

def guncel_kurlari_cek():
    """Açık kaynaklı döviz API'lerinden (Frankfurter ECB & Open ER-API) anlık USD/TRY ve EUR/TRY kurlarını çeker."""
    global USD_KUR, EUR_KUR, KUR_KAYNAK
    try:
        r_usd = tls_requests.get("https://api.frankfurter.dev/v1/latest?from=USD&to=TRY", timeout=8)
        r_eur = tls_requests.get("https://api.frankfurter.dev/v1/latest?from=EUR&to=TRY", timeout=8)
        if r_usd.status_code == 200 and r_eur.status_code == 200:
            u = float(r_usd.json().get("rates", {}).get("TRY", 0))
            e = float(r_eur.json().get("rates", {}).get("TRY", 0))
            if u > 10 and e > 10:
                USD_KUR = round(u, 4)
                EUR_KUR = round(e, 4)
                KUR_KAYNAK = "Frankfurter (ECB Açık Kaynak)"
                return
    except Exception:
        pass

    try:
        r_open = tls_requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        if r_open.status_code == 200:
            rates = r_open.json().get("rates", {})
            try_rate = float(rates.get("TRY", 0))
            eur_rate = float(rates.get("EUR", 0))
            if try_rate > 10 and eur_rate > 0:
                USD_KUR = round(try_rate, 4)
                EUR_KUR = round(try_rate / eur_rate, 4)
                KUR_KAYNAK = "Open ER-API"
                return
    except Exception:
        pass

def gorunur_mu(etiket):
    for el in [etiket] + list(etiket.parents):
        if not hasattr(el, "get"):
            continue
        siniflar = el.get("class", []) or []
        if any(c in GIZLI_ISARETLERI for c in siniflar):
            return False
        stil = (el.get("style", "") or "").replace(" ", "").lower()
        if "display:none" in stil or "visibility:hidden" in stil:
            return False
        if el.has_attr("hidden"):
            return False
    return True

def tl_formatla(tl_deger):
    if tl_deger < 1:
        return f"{tl_deger:.4f} TL"
    return f"{tl_deger:.2f} TL"

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Tükendi" in fiyat_str or "Stokta" in fiyat_str:
        return 999999.0
    ust = fiyat_str.upper()
    carpan = USD_KUR if ("$" in ust or "USD" in ust) else (EUR_KUR if ("€" in ust or "EUR" in ust) else 1.0)
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c in ',.')
    if ',' in temiz and '.' in temiz:
        if temiz.rfind(',') > temiz.rfind('.'):
            temiz = temiz.replace('.', '').replace(',', '.')
        else:
            temiz = temiz.replace(',', '')
    elif ',' in temiz:
        temiz = temiz.replace(',', '.')
    try:
        return float(temiz) * carpan
    except Exception:
        return 999999.0

def metni_sayiya_cevir(fiyat_metni):
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni)
    if ',' in temiz and '.' in temiz:
        if temiz.rfind(',') > temiz.rfind('.'):
            temiz = temiz.replace('.', '').replace(',', '.')
        else:
            temiz = temiz.replace(',', '')
    elif ',' in temiz:
        temiz = temiz.replace(',', '.')
    try:
        return float(temiz)
    except Exception:
        return None

def ozdisan_tara(ad, ayarlar, ham_sorgu):
    bulunanlar = []
    q_encoded = urllib.parse.quote(ham_sorgu.strip())
    arama_url = ayarlar["url_sablonu"].format(q_encoded)
    kategori_adi = ayarlar["kategori"]

    try:
        res = tls_requests.get(arama_url, headers=TR_HEADERS, impersonate="chrome110", timeout=15)
        if res.status_code != 200:
            return bulunanlar

        soup = BeautifulSoup(res.text, 'html.parser')
        ps_link_etiketi = soup.select_one('a[href*="/ps/"]')
        if not ps_link_etiketi:
            return bulunanlar

        ps_href = ps_link_etiketi.get("href", "")
        if not ps_href.startswith("http"):
            ps_url = ayarlar["base_url"] + (ps_href if ps_href.startswith("/") else "/" + ps_href)
        else:
            ps_url = ps_href

        res_ps = tls_requests.get(ps_url, headers=TR_HEADERS, impersonate="chrome110", timeout=15)
        if res_ps.status_code != 200:
            return bulunanlar

        soup_ps = BeautifulSoup(res_ps.text, 'html.parser')
        for sc in soup_ps.find_all("script", type="application/ld+json"):
            try:
                veri = json.loads(sc.string or "")
                if veri.get("@type") == "ItemList" and "itemListElement" in veri:
                    for el in veri["itemListElement"][:8]:
                        urun_bilgi = el.get("item", el)
                        isim = urun_bilgi.get("name", "").strip()
                        aciklama = urun_bilgi.get("description", "").strip()
                        tam_isim = f"{isim} ({aciklama})" if (aciklama and aciklama not in isim) else isim

                        link = urun_bilgi.get("url", ps_url)
                        offers = urun_bilgi.get("offers", [])
                        offer = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else {})

                        fiyat_deger = offer.get("price")
                        para_birimi = offer.get("priceCurrency", "TRY").upper()
                        stok_var = "InStock" in str(offer.get("availability", ""))

                        sayi = None
                        if fiyat_deger is not None:
                            try:
                                sayi = float(str(fiyat_deger).replace(",", "."))
                            except Exception:
                                sayi = None

                        if stok_var and sayi and sayi > 0:
                            if para_birimi == "USD":
                                sayi_tl = sayi * USD_KUR
                            elif para_birimi == "EUR":
                                sayi_tl = sayi * EUR_KUR
                            else:
                                sayi_tl = sayi
                            fiyat_gosterim = tl_formatla(sayi_tl)
                            stok_durum = "Canlı Veri"
                        else:
                            fiyat_gosterim = "Tükendi"
                            stok_durum = "Tükendi"

                        bulunanlar.append({
                            "tedarikci": ad, "Tedarikci": ad,
                            "Kategori": kategori_adi, "kategori": kategori_adi,
                            "urun_adi": tam_isim, "Urun": tam_isim,
                            "fiyat_metni": fiyat_gosterim, "Fiyat": fiyat_gosterim,
                            "canli": (stok_durum == "Canlı Veri"), "Durum": stok_durum,
                            "url": link, "Link": link
                        })
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"[{ad}] HATA: {str(e)}")

    return bulunanlar

def site_tara(ad, ayarlar, ham_sorgu):
    if ayarlar["seciciler"].get("kutu") == "ozdisan_ozel":
        return ozdisan_tara(ad, ayarlar, ham_sorgu)

    bulunanlar = []
    kategori_adi = ayarlar["kategori"]
    sec = ayarlar["seciciler"]

    sorgu_adaylari = [ham_sorgu.strip()]
    if ad == "Merter Elektronik":
        ayrik = re.sub(r'^([A-Za-z]+)(\d+.*)$', r'\1 \2', ham_sorgu.strip())
        if ayrik != ham_sorgu.strip():
            sorgu_adaylari.insert(0, ayrik)

    for aktif_sorgu in sorgu_adaylari:
        q_encoded = urllib.parse.quote(aktif_sorgu)
        url = ayarlar["url_sablonu"].format(q_encoded)

        try:
            res = tls_requests.get(url, headers=TR_HEADERS, impersonate="chrome110", timeout=15)

            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                urunler = soup.select(sec["kutu"])

                if not urunler:
                    detay_kartlari = soup.select(".product-detail-card")
                    if detay_kartlari:
                        urunler = [kart.parent for kart in detay_kartlari if kart.parent]

                eklenen_isimler = set()
                sayac = 0

                for urun in urunler:
                    if sayac >= 8:
                        break

                    try:
                        isim = ""
                        link = url

                        title_elem = urun.select_one(
                            '.showcase-title a, a.vitrin-product-title, .productName a, .detailLink, '
                            '.product-title, [data-qa="product-title"], .productName, .product-name, .ems-prd-name'
                        )
                        if title_elem:
                            isim = (title_elem.get("title") or title_elem.text or "").replace("Yeni", "").replace("YENİ", "").strip()
                            if title_elem.name == 'a' and title_elem.has_attr('href'):
                                link = title_elem['href']
                            else:
                                a_tag = title_elem.find('a') or urun.find('a', href=True)
                                if a_tag and a_tag.get('href') and a_tag['href'] != "#":
                                    link = a_tag['href']

                        if len(isim) < 3:
                            for a in urun.find_all('a'):
                                text = (a.get("title") or a.text or "").replace("Yeni", "").replace("YENİ", "").strip()
                                text = re.sub(r'\{.*?\}', '', text)
                                lower_text = text.lower()

                                yasakli_kelimeler = [
                                    "incele", "sepete ekle", "favori", "karşılaştır", "karsilastir",
                                    "listeye", "stokta", "tükendi", "kargo", "haber ver", "hızlı al", "satın al"
                                ]

                                if len(text) > len(isim) and not any(y in lower_text for y in yasakli_kelimeler):
                                    isim = text
                                    temp_link = a.get('href', '')
                                    if temp_link and temp_link != "#":
                                        link = temp_link

                        isim = re.sub(r'\s+', ' ', isim).strip()

                        if len(isim) < 3 or isim in eklenen_isimler:
                            continue

                        if link and not link.startswith('http'):
                            link = ayarlar["base_url"] + link if link.startswith('/') else ayarlar["base_url"] + '/' + link

                        stokta_yok_mu = False

                        aday = urun.select_one(
                            '.out-of-stock, .stock-out, .no-stock, .tukendi, .sold-out, '
                            '.sold-out-label, .no-stock-button, .ems-prd-badge-tukendi, .product-out-of-stock'
                        )
                        if aday and gorunur_mu(aday):
                            stokta_yok_mu = True

                        if not stokta_yok_mu:
                            for etiket in urun.find_all(['div', 'span', 'a', 'p', 'b', 'button']):
                                metin = etiket.text.strip().lower()
                                if metin in ["tükendi", "stokta yok", "tükendi̇", "gelince haber ver"] and gorunur_mu(etiket):
                                    stokta_yok_mu = True
                                    break

                        fiyat_gosterim = "Tükendi"
                        stok_durum = "Tükendi"

                        fiyat_kutu = urun.select_one('.showcase-price-new, .currentPrice, .discountPriceSpan, .product-price, .ems-prd-price')
                        fiyat_kaynak_metin = fiyat_kutu.text if fiyat_kutu else urun.text
                        raw_text = fiyat_kaynak_metin.replace('\n', ' ')
                        raw_text = re.sub(r'\{.*?\}', '', raw_text)

                        if not stokta_yok_mu:
                            fiyat_eslesmeler = re.findall(
                                r'(?:TL|₺|tl|USD|\$|EUR|€)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl|USD|\$|EUR|€)',
                                raw_text, re.IGNORECASE
                            )
                            if not fiyat_eslesmeler and fiyat_kutu:
                                raw_all = re.sub(r'\{.*?\}', '', urun.text.replace('\n', ' '))
                                fiyat_eslesmeler = re.findall(
                                    r'(?:TL|₺|tl|USD|\$|EUR|€)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl|USD|\$|EUR|€)',
                                    raw_all, re.IGNORECASE
                                )

                            gecerli = []
                            for e in fiyat_eslesmeler:
                                sayi = metni_sayiya_cevir(e)
                                if sayi and sayi > 0:
                                    saf = e.upper()
                                    if "$" in saf or "USD" in saf:
                                        sayi_tl = sayi * USD_KUR
                                    elif "€" in saf or "EUR" in saf:
                                        sayi_tl = sayi * EUR_KUR
                                    else:
                                        sayi_tl = sayi
                                    gecerli.append(sayi_tl)

                            if gecerli:
                                gecerli.sort()
                                fiyat_gosterim = tl_formatla(gecerli[0])
                                stok_durum = "Canlı Veri"
                            else:
                                alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', raw_text)
                                if alternatif_sayi:
                                    fiyat_gosterim = alternatif_sayi.group(0) + " TL"
                                    stok_durum = "Canlı Veri"

                        if not stokta_yok_mu and stok_durum == "Tükendi":
                            continue

                        if "0,00" in fiyat_gosterim or "0.00" in fiyat_gosterim:
                            fiyat_gosterim = "Tükendi"
                            stok_durum = "Tükendi"

                        eklenen_isimler.add(isim)

                        bulunanlar.append({
                            "tedarikci": ad, "Tedarikci": ad,
                            "Kategori": kategori_adi, "kategori": kategori_adi,
                            "urun_adi": isim, "Urun": isim,
                            "fiyat_metni": fiyat_gosterim, "Fiyat": fiyat_gosterim,
                            "canli": (stok_durum == "Canlı Veri"), "Durum": stok_durum,
                            "url": link, "Link": link
                        })
                        sayac += 1
                    except Exception:
                        continue
        except Exception as e:
            print(f"[{ad}] HATA: {str(e)}")

        if bulunanlar:
            break

    return bulunanlar

class AIProjeIstegi(BaseModel):
    prompt: str

SISTEM_TALIMATI = (
    "Sen KomponentBul elektronik komponent karşılaştırma platformunun uzman elektronik ve robotik mühendisi "
    "yapay zeka asistanısın. Kullanıcı bir proje, robot veya devre yapmak istediğinde Türkçe olarak kısa, "
    "anlaşılır bir proje özeti yaz ve gereken temel elektronik malzemeleri listele. "
    "Her malzemenin 'arama_kodu' alanına Türkiye'deki elektronik sitelerinde aratıldığında doğrudan "
    "ürünü bulacak kısa ve standart parça adını/kodunu yaz (Örn: 'Arduino Uno', 'L298N', 'SG90 Servo', "
    "'HC-SR04', 'TCRT5000', 'LM358', 'BC547'). En fazla 6 temel malzeme öner. "
    "Yanıtı SADECE şu JSON şemasında ver: "
    '{"aciklama": "Proje özeti...", "malzemeler": [{"ad": "...", "arama_kodu": "...", "adet": "...", "gorev": "..."}]}'
)

def gemini_yetkili_model_ile_uret(api_key: str, kullanici_prompt: str):
    """API anahtarının Google AI Studio'da yetkili olduğu modelleri otomatik tespit edip JSON yanıt üretir."""
    aday_modeller = []
    try:
        r_models = tls_requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=10
        )
        if r_models.status_code == 200:
            for m in r_models.json().get("models", []):
                isim = m.get("name", "")
                metodlar = m.get("supportedGenerationMethods", [])
                if "generateContent" in metodlar and "gemini" in isim.lower():
                    aday_modeller.append(isim)
    except Exception:
        pass

    # Flash modellerini öne al
    aday_modeller.sort(key=lambda x: (0 if "flash" in x.lower() else 1, x))
    for varsayilan in ["models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-flash"]:
        if varsayilan not in aday_modeller:
            aday_modeller.append(varsayilan)

    son_hata = "Uygun model bulunamadı"
    for model_yolu in aday_modeller[:5]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_yolu}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": SISTEM_TALIMATI}]},
            "contents": [{"role": "user", "parts": [{"text": kullanici_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            r = tls_requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                adaylar = r.json().get("candidates", [])
                if adaylar:
                    metin = adaylar[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    temiz_json = re.sub(r"^```(?:json)?|```$", "", metin.strip(), flags=re.MULTILINE).strip()
                    return json.loads(temiz_json)
            else:
                son_hata = f"{model_yolu} -> HTTP {r.status_code}"
        except Exception as e:
            son_hata = str(e)
            continue

    raise RuntimeError(son_hata)

@app.post("/ai-asistan")
def ai_proje_asistani(istek: AIProjeIstegi):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "hata": "Sunucuda GEMINI_API_KEY tanımlı değil. Lütfen Render Environment Variables kısmına GEMINI_API_KEY ekleyin."
        }

    # 1. Birincil SDK denemesi
    try:
        client = genai.Client(api_key=api_key)
        interaction = client.interactions.create(
            model="gemini-3.8-flash",
            store=False,
            system_instruction=SISTEM_TALIMATI,
            input=istek.prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": {
                    "type": "object",
                    "properties": {
                        "aciklama": {"type": "string"},
                        "malzemeler": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "ad": {"type": "string"},
                                    "arama_kodu": {"type": "string"},
                                    "adet": {"type": "string"},
                                    "gorev": {"type": "string"}
                                },
                                "required": ["ad", "arama_kodu", "adet", "gorev"]
                            }
                        }
                    },
                    "required": ["aciklama", "malzemeler"]
                }
            }
        )
        return json.loads(interaction.output_text)
    except Exception:
        # 2. Ücretsiz API Anahtarı Yetkili Model Otomatik Yedeği (403 Permission Denied Çözümü)
        try:
            return gemini_yetkili_model_ile_uret(api_key, istek.prompt)
        except Exception as e2:
            return {"hata": f"Yapay zeka yanıt üretirken hata oluştu: {str(e2)}"}

@app.get("/ping")
def sunucu_durumu():
    return {
        "durum": "aktif",
        "kurlar": {
            "USD": round(USD_KUR, 2),
            "EUR": round(EUR_KUR, 2),
            "kaynak": KUR_KAYNAK
        }
    }

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

@app.get("/arama")
def arama_yap(q: str, kategori: str = "Hepsi"):
    sonuclar = []
    kategori_kucuk = kategori.strip().lower()

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        gelecek_sonuclar = []
        for ad, ayarlar in TEDARIKCILER.items():
            site_kategori = ayarlar["kategori"].strip().lower()

            if kategori_kucuk not in ["hepsi", "tümü", "tumu", ""]:
                if site_kategori != kategori_kucuk:
                    continue

            gelecek_sonuclar.append(executor.submit(site_tara, ad, ayarlar, q))

        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            sonuclar.extend(gelecek.result())

    gorulmus_linkler = set()
    benzersiz_sonuclar = []
    for s in sonuclar:
        anahtar = s.get("url")
        if anahtar in gorulmus_linkler:
            continue
        gorulmus_linkler.add(anahtar)
        benzersiz_sonuclar.append(s)
    sonuclar = benzersiz_sonuclar

    sonuclar.sort(key=lambda x: fiyat_temizle(x["fiyat_metni"]))
    return {
        "sonuclar": sonuclar,
        "kurlar": {
            "USD": round(USD_KUR, 2),
            "EUR": round(EUR_KUR, 2),
            "kaynak": KUR_KAYNAK
        }
    }

def arka_plan_gorevleri():
    guncel_kurlari_cek()
    sayac = 0
    while True:
        time.sleep(600)
        sayac += 1
        try:
            tls_requests.get("https://komponentbul.onrender.com/ping", timeout=10)
        except Exception:
            pass
        if sayac % 3 == 0:
            guncel_kurlari_cek()

@app.on_event("startup")
def baslangic_gorevi():
    t = threading.Thread(target=arka_plan_gorevleri, daemon=True)
    t.start()
