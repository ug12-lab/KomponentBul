from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup
import urllib.parse
import urllib.request
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

ARAMA_ONBELLEK = {}
ONBELLEK_SURESI = 1800  # 30 dakika
AI_OGRENME_HAFIZASI = {}
AKTIF_AI_MODEL = None

EGITILMIS_PROJELER = [
    {
        "anahtarlar": ["çizgi", "cizgi", "izleyen", "çizen"],
        "veri": {
            "aciklama": "Çizgi çizen / izleyen robot; zemindeki çizgiyi kızılötesi sensörlerle algılayıp motor sürücü üzerinden tekerlekleri ve kalem servosunu kontrol eder.",
            "malzemeler": [
                {"ad": "Arduino Uno R3 Anakart", "arama_kodu": "Arduino Uno", "adet": "1 Adet", "gorev": "Sensör verilerini işleyip motorları yöneten ana kontrolcü"},
                {"ad": "L298N Çift Kanallı Motor Sürücü", "arama_kodu": "L298N", "adet": "1 Adet", "gorev": "DC motorların hız ve yön kontrolü"},
                {"ad": "TCRT5000 Kızılötesi Çizgi Sensörü", "arama_kodu": "TCRT5000", "adet": "2 Adet", "gorev": "Zemindeki çizgiyi algılama"},
                {"ad": "SG90 Mikro Servo Motor", "arama_kodu": "SG90", "adet": "1 Adet", "gorev": "Kalemi indirip kaldırma mekanizması"}
            ]
        }
    },
    {
        "anahtarlar": ["engel", "kaça", "kaca", "ultrasonik", "mesafe", "park"],
        "veri": {
            "aciklama": "Engelden kaçan robot; ultrasonik ses dalgalarıyla önündeki engelin uzaklığını ölçüp çarpmadan otomatik yön değiştirir.",
            "malzemeler": [
                {"ad": "Arduino Uno R3", "arama_kodu": "Arduino Uno", "adet": "1 Adet", "gorev": "Mesafe hesaplama ve karar verme birimi"},
                {"ad": "HC-SR04 Ultrasonik Mesafe Sensörü", "arama_kodu": "HC-SR04", "adet": "1 Adet", "gorev": "Engel mesafesini santimetre olarak ölçme"},
                {"ad": "L298N Motor Sürücü Kartı", "arama_kodu": "L298N", "adet": "1 Adet", "gorev": "Tekerlek motorlarını sürme"},
                {"ad": "SG90 Servo Motor", "arama_kodu": "SG90", "adet": "1 Adet", "gorev": "Sensörü sağa-sola döndürerek tarama yapma"}
            ]
        }
    },
    {
        "anahtarlar": ["5v", "güç kaynağı", "guc kaynagi", "regüle", "regule", "7805", "adaptör"],
        "veri": {
            "aciklama": "5V regüleli doğru akım güç kaynağı; 9V-12V giriş gerilimini mikrodenetleyiciler için sabit 5V çıkışa dönüştürür.",
            "malzemeler": [
                {"ad": "L7805CV 5V Voltaj Regülatörü", "arama_kodu": "L7805", "adet": "1 Adet", "gorev": "Gerilimi sabit 5V seviyesine düşürme"},
                {"ad": "1N4007 Doğrultucu Diyot", "arama_kodu": "1N4007", "adet": "4 Adet", "gorev": "Ters kutup koruması ve doğrultma"},
                {"ad": "100uF Elektrolitik Kondansatör", "arama_kodu": "100uF", "adet": "2 Adet", "gorev": "Gerilim dalgalanmalarını filtreleme"},
                {"ad": "5mm Kırmızı LED", "arama_kodu": "5mm LED", "adet": "1 Adet", "gorev": "Güç açık gösterge ışığı"}
            ]
        }
    },
    {
        "anahtarlar": ["sulama", "toprak", "nem", "bitki", "çiçek"],
        "veri": {
            "aciklama": "Otomatik bitki sulama sistemi; toprağın nem oranını ölçerek toprak kuruduğunda röle yardımıyla su motorunu çalıştırır.",
            "malzemeler": [
                {"ad": "Arduino Uno R3", "arama_kodu": "Arduino Uno", "adet": "1 Adet", "gorev": "Nem verisini okuyup pompayı tetikleme"},
                {"ad": "Toprak Nem Sensörü Modülü", "arama_kodu": "Toprak Nem", "adet": "1 Adet", "gorev": "Topraktaki ıslaklık seviyesini ölçme"},
                {"ad": "5V Tek Kanallı Röle Kartı", "arama_kodu": "5V Role", "adet": "1 Adet", "gorev": "Su pompasını güvenli şekilde açıp kapatma"},
                {"ad": "Mini Dalgıç Su Pompası", "arama_kodu": "Su Pompasi", "adet": "1 Adet", "gorev": "Hazneden toprağa su aktarma"}
            ]
        }
    },
    {
        "anahtarlar": ["akıllı ev", "akilli ev", "iot", "wifi", "esp32", "esp8266"],
        "veri": {
            "aciklama": "Wi-Fi tabanlı Akıllı Ev ve IoT sistemi; telefon üzerinden cihazları açıp kapatır ve oda sıcaklığını canlı izler.",
            "malzemeler": [
                {"ad": "ESP32 Wi-Fi + Bluetooth Kartı", "arama_kodu": "ESP32", "adet": "1 Adet", "gorev": "Kablosuz internet bağlantısı ve ana işlemci"},
                {"ad": "DHT11 Sıcaklık ve Nem Sensörü", "arama_kodu": "DHT11", "adet": "1 Adet", "gorev": "Ortam sıcaklık ve nem ölçümü"},
                {"ad": "5V Röle Modülü", "arama_kodu": "5V Role", "adet": "1 Adet", "gorev": "Ev cihazlarını anahtarlama"},
                {"ad": "Breadboard Devre Tahtası", "arama_kodu": "Breadboard", "adet": "1 Adet", "gorev": "Lehimsiz devre kurulumu"}
            ]
        }
    },
    {
        "anahtarlar": ["alarm", "hırsız", "hirsiz", "hareket", "pir", "yangın", "gaz", "duman"],
        "veri": {
            "aciklama": "Güvenlik ve alarm devresi; ortamdaki hareketi veya gaz/duman sızıntısını algılayarak sesli buzzer ile uyarı verir.",
            "malzemeler": [
                {"ad": "HC-SR501 PIR Hareket Sensörü", "arama_kodu": "HC-SR501", "adet": "1 Adet", "gorev": "İnsan hareketini algılama"},
                {"ad": "MQ-2 Gaz ve Duman Sensörü", "arama_kodu": "MQ-2", "adet": "1 Adet", "gorev": "Yanıcı gaz ve duman tespiti"},
                {"ad": "5V Aktif Buzzer", "arama_kodu": "Buzzer", "adet": "1 Adet", "gorev": "Sesli siren uyarısı"},
                {"ad": "BC547 NPN Transistör", "arama_kodu": "BC547", "adet": "1 Adet", "gorev": "Buzzer akımını anahtarlama"}
            ]
        }
    },
    {
        "anahtarlar": ["çakar", "cakar", "flip", "flop", "ne555", "555", "flaşör", "led yak"],
        "veri": {
            "aciklama": "NE555 entegreli çakar / flip-flop LED devresi; ayarlanabilir hızda sırayla yanıp sönen sinyal devresidir.",
            "malzemeler": [
                {"ad": "NE555 Zamanlayıcı Entegresi", "arama_kodu": "NE555", "adet": "1 Adet", "gorev": "Kare dalga saat sinyali üretme"},
                {"ad": "BC547 NPN Transistör", "arama_kodu": "BC547", "adet": "2 Adet", "gorev": "LED gruplarını anahtarlama"},
                {"ad": "5mm Kırmızı LED", "arama_kodu": "5mm LED", "adet": "4 Adet", "gorev": "Görsel ışık çıkışı"},
                {"ad": "220 Ohm Direnç", "arama_kodu": "220 Ohm", "adet": "4 Adet", "gorev": "LED akım sınırlama koruması"}
            ]
        }
    },
    {
        "anahtarlar": ["bluetooth", "araba", "rc araba", "hc-05", "hc05"],
        "veri": {
            "aciklama": "Bluetooth kontrollü robot araba; telefondan gönderilen yön komutlarını Bluetooth modülüyle alıp motorları sürer.",
            "malzemeler": [
                {"ad": "Arduino Uno R3", "arama_kodu": "Arduino Uno", "adet": "1 Adet", "gorev": "Komutları çözüp motorları yönetme"},
                {"ad": "HC-05 Bluetooth Modülü", "arama_kodu": "HC-05", "adet": "1 Adet", "gorev": "Telefon ile kablosuz haberleşme"},
                {"ad": "L298N Motor Sürücü", "arama_kodu": "L298N", "adet": "1 Adet", "gorev": "Motor hız ve yön kontrolü"},
                {"ad": "6V Redüktörlü DC Motor", "arama_kodu": "DC Motor", "adet": "2 Adet", "gorev": "Tekerlek tahriki"}
            ]
        }
    }
]

def guncel_kurlari_cek():
    global USD_KUR, EUR_KUR, KUR_KAYNAK
    try:
        r_usd = tls_requests.get("https://api.frankfurter.dev/v1/latest?from=USD&to=TRY", timeout=6)
        r_eur = tls_requests.get("https://api.frankfurter.dev/v1/latest?from=EUR&to=TRY", timeout=6)
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
        r_open = tls_requests.get("https://open.er-api.com/v6/latest/USD", timeout=6)
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

def ozdisan_tara(ad, ayarlar, ham_sorgu, zaman_asimi=5):
    bulunanlar = []
    q_encoded = urllib.parse.quote(ham_sorgu.strip())
    arama_url = ayarlar["url_sablonu"].format(q_encoded)
    kategori_adi = ayarlar["kategori"]

    try:
        res = tls_requests.get(arama_url, headers=TR_HEADERS, impersonate="chrome110", timeout=zaman_asimi)
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

        res_ps = tls_requests.get(ps_url, headers=TR_HEADERS, impersonate="chrome110", timeout=zaman_asimi)
        if res_ps.status_code != 200:
            return bulunanlar

        soup_ps = BeautifulSoup(res_ps.text, 'html.parser')
        for sc in soup_ps.find_all("script", type="application/ld+json"):
            try:
                veri = json.loads(sc.string or "")
                if veri.get("@type") == "ItemList" and "itemListElement" in veri:
                    for el in veri["itemListElement"][:6]:
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
    except Exception:
        pass

    return bulunanlar

def site_tara(ad, ayarlar, ham_sorgu, zaman_asimi=5):
    if ayarlar["seciciler"].get("kutu") == "ozdisan_ozel":
        return ozdisan_tara(ad, ayarlar, ham_sorgu, zaman_asimi)

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
            res = tls_requests.get(url, headers=TR_HEADERS, impersonate="chrome110", timeout=zaman_asimi)

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
                    if sayac >= 6:
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
                                    "listeye", "stokta", "tükendi", "kargo", "haber ver", "hızlı al", "satın al", "bugünkargoda", "bugün kargoda"
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
        except Exception:
            pass

        if bulunanlar:
            break

    return bulunanlar

class AIProjeIstegi(BaseModel):
    prompt: str

SISTEM_TALIMATI = (
    "Sen KomponentBul elektronik komponent karşılaştırma platformunun uzman elektronik mühendisi "
    "yapay zeka asistanısın. Kullanıcının istediği devre veya proje için 1-2 cümlelik kısa bir Türkçe özet yaz "
    "ve gereken EN TEMEL 4 elektronik malzemeyi listele. "
    "Her malzemenin 'arama_kodu' alanına Türkiye'deki elektronik sitelerinde aratıldığında doğrudan "
    "ürünü bulacak kısa standart kodu yaz (Örn: 'Arduino Uno', 'L298N', 'SG90', 'HC-SR04', 'TCRT5000', "
    "'L7805', 'LM358', 'BC547', 'NE555', 'ESP32', 'DHT11', 'Buzzer'). "
    "Yanıtı SADECE şu JSON şemasında ver: "
    '{"aciklama": "Proje özeti...", "malzemeler": [{"ad": "...", "arama_kodu": "...", "adet": "...", "gorev": "..."}]}'
)

def egitilmis_projelerden_bul(prompt_metni: str):
    temiz = prompt_metni.strip().lower()
    if temiz in AI_OGRENME_HAFIZASI:
        return AI_OGRENME_HAFIZASI[temiz]

    for kayit in EGITILMIS_PROJELER:
        for anahtar in kayit["anahtarlar"]:
            if anahtar in temiz:
                return kayit["veri"]
    return None

def gemini_ultra_hizli_uret(api_key: str, kullanici_prompt: str):
    """En güncel Gemini Flash-Lite ve 2.5 Flash modellerini sıfır düşünme gecikmesiyle (1 sn) çağırır."""
    global AKTIF_AI_MODEL

    oncelikli_modeller = [
        "models/gemini-2.5-flash-lite",
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash"
    ]
    if AKTIF_AI_MODEL and AKTIF_AI_MODEL in oncelikli_modeller:
        oncelikli_modeller.remove(AKTIF_AI_MODEL)
        oncelikli_modeller.insert(0, AKTIF_AI_MODEL)

    son_hata = "Model yanıt vermedi"
    for model_yolu in oncelikli_modeller:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_yolu}:generateContent?key={api_key}"
        gen_config = {
            "responseMimeType": "application/json",
            "maxOutputTokens": 400,
            "temperature": 0.2
        }
        if "2.5" in model_yolu:
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}

        payload = {
            "systemInstruction": {"parts": [{"text": SISTEM_TALIMATI}]},
            "contents": [{"role": "user", "parts": [{"text": kullanici_prompt}]}],
            "generationConfig": gen_config
        }
        veri_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=veri_bytes, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    yanit_json = json.loads(resp.read().decode("utf-8"))
                    adaylar = yanit_json.get("candidates", [])
                    if adaylar:
                        AKTIF_AI_MODEL = model_yolu
                        metin = adaylar[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        temiz_json = re.sub(r"^```(?:json)?|```$", "", metin.strip(), flags=re.MULTILINE).strip()
                        sonuc = json.loads(temiz_json)
                        AI_OGRENME_HAFIZASI[kullanici_prompt.strip().lower()] = sonuc
                        return sonuc
        except Exception as e:
            son_hata = f"{model_yolu}: {str(e)}"
            continue

    raise RuntimeError(son_hata)

@app.post("/ai-asistan")
def ai_proje_asistani(istek: AIProjeIstegi):
    hazir_yanit = egitilmis_projelerden_bul(istek.prompt)
    if hazir_yanit:
        return hazir_yanit

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "hata": "Sunucuda GEMINI_API_KEY tanımlı değil. Lütfen Render Environment Variables kısmına GEMINI_API_KEY ekleyin."
        }

    try:
        return gemini_ultra_hizli_uret(api_key, istek.prompt)
    except Exception:
        try:
            client = genai.Client(api_key=api_key)
            interaction = client.interactions.create(
                model="gemini-3.8-flash",
                store=False,
                system_instruction=SISTEM_TALIMATI,
                input=istek.prompt
            )
            sonuc = json.loads(interaction.output_text)
            AI_OGRENME_HAFIZASI[istek.prompt.strip().lower()] = sonuc
            return sonuc
        except Exception as e2:
            return {"hata": f"Yapay zeka yanıt üretirken hata oluştu: {str(e2)}"}

@app.get("/ping")
def sunucu_durumu():
    return {
        "durum": "aktif",
        "aktif_model": AKTIF_AI_MODEL or "Hazır",
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
def arama_yap(q: str, kategori: str = "Hepsi", hizli: int = 0):
    simdi = time.time()
    onbellek_anahtari = f"{q.strip().lower()}_{kategori.strip().lower()}"

    if onbellek_anahtari in ARAMA_ONBELLEK:
        kayit_zamani, kayitli_sonuc = ARAMA_ONBELLEK[onbellek_anahtari]
        if simdi - kayit_zamani < ONBELLEK_SURESI:
            return {
                "sonuclar": kayitli_sonuc,
                "kurlar": {"USD": round(USD_KUR, 2), "EUR": round(EUR_KUR, 2), "kaynak": KUR_KAYNAK}
            }

    sonuclar = []
    kategori_kucuk = kategori.strip().lower()
    site_timeout = 3 if hizli == 1 else 5

    with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
        gelecek_sonuclar = []
        for ad, ayarlar in TEDARIKCILER.items():
            site_kategori = ayarlar["kategori"].strip().lower()

            if kategori_kucuk not in ["hepsi", "tümü", "tumu", ""]:
                if site_kategori != kategori_kucuk:
                    continue

            gelecek_sonuclar.append(executor.submit(site_tara, ad, ayarlar, q, site_timeout))

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
    if sonuclar:
        ARAMA_ONBELLEK[onbellek_anahtari] = (simdi, sonuclar)

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
