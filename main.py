from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures
import re
from curl_cffi import requests as tls_requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".ems-prd, .product-item, div[class*='product']"}
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
        "seciciler": {"kutu": ".showcase, div[class*='product'], li[class*='product']"}
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box"}
    },
    "Direnç.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Kartal Otomasyon": {
        "url_sablonu": "https://www.kartalotomasyon.com.tr/arama?q={}",
        "base_url": "https://www.kartalotomasyon.com.tr",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Komponentci": {
        "url_sablonu": "https://www.komponentci.net/Arama.aspx?kelime={}",
        "base_url": "https://www.komponentci.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".productItem, .showcase, div[class*='product']"}
    },
    "Samm Market": {
        "url_sablonu": "https://market.samm.com/search?q={}",
        "base_url": "https://market.samm.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-card, div[class*='product'], a[class*='product']"}
    },
    "Merter Elektronik": {
        "url_sablonu": "https://www.merterelektronik.com/Arama.aspx?kelime={}",
        "base_url": "https://www.merterelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".productItem, .showcase, div[class*='product']"}
    },
    "Özdisan": {
        "url_sablonu": "https://ozdisan.com/Search?q={}",
        "base_url": "https://ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, div[class*='product']"}
    },
    "Empastore": {
        "url_sablonu": "https://www.empastore.com/arama?q={}",
        "base_url": "https://www.empastore.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, .showcase, div[class*='product']"}
    },
    "Karaköy Elektronik": {
        "url_sablonu": "https://www.karakoyelektronik.com/arama?q={}",
        "base_url": "https://www.karakoyelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "F1 Depo": {
        "url_sablonu": "https://www.f1depo.com/arama?q={}",
        "base_url": "https://www.f1depo.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Elektrovadi": {
        "url_sablonu": "https://www.elektrovadi.com/arama?q={}",
        "base_url": "https://www.elektrovadi.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    }
}

GIZLI_ISARETLERI = {"d-none", "hidden", "invisible", "display-none", "hide"}

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

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Tükendi" in fiyat_str or "Stokta" in fiyat_str:
        return 999999.0
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c in ',.')
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except Exception:
        return 999999.0

def metni_sayiya_cevir(fiyat_metni):
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni)
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except Exception:
        return None

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url_sablonu"].format(q_encoded)
    sec = ayarlar["seciciler"]

    try:
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])

            eklenen_isimler = set()
            sayac = 0

            for urun in urunler:
                if sayac >= 8:
                    break

                try:
                    isim = ""
                    link = url

                    title_elem = urun.select_one('.productName a, .product-title, [data-qa="product-title"], .productName, .product-name')
                    if title_elem:
                        isim = title_elem.text.replace("Yeni", "").replace("YENİ", "").strip()
                        if title_elem.name == 'a' and title_elem.has_attr('href'):
                            link = title_elem['href']
                        else:
                            for a in urun.find_all('a'):
                                if a.has_attr('href') and a['href'] != "#":
                                    link = a['href']
                                    break
                    
                    if len(isim) < 3:
                        for a in urun.find_all('a'):
                            text = a.text.replace("Yeni", "").replace("YENİ", "").strip()
                            text = re.sub(r'\{.*?\}', '', text)
                            lower_text = text.lower()
                            
                            yasakli_kelimeler = ["incele", "sepete ekle", "favori", "karşılaştır", "karsilastir", "listeye", "stokta", "tükendi", "kargo", "haber ver", "hızlı al", "satın al"]
                            
                            if len(text) > len(isim) and not any(y in lower_text for y in yasakli_kelimeler):
                                isim = text
                                temp_link = a.get('href', '')
                                if temp_link:
                                    link = temp_link

                    isim = re.sub(r'\s+', ' ', isim).strip()

                    if len(isim) < 3 or isim in eklenen_isimler:
                        continue

                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link if link.startswith('/') else ayarlar["base_url"] + '/' + link

                    stokta_yok_mu = False

                    aday = urun.select_one('.out-of-stock, .stock-out, .no-stock, .tukendi, .sold-out, .ems-prd-badge-tukendi, .product-out-of-stock')
                    if aday and gorunur_mu(aday):
                        stokta_yok_mu = True

                    if not stokta_yok_mu:
                        for etiket in urun.find_all(['div', 'span', 'a', 'p', 'b', 'button']):
                            metin = etiket.text.strip().lower()
                            if metin in ["tükendi", "stokta yok", "tükendi̇"] and gorunur_mu(etiket):
                                stokta_yok_mu = True
                                break

                    fiyat_gosterim = "Tükendi"
                    stok_durum = "Tükendi"

                    raw_text = urun.text.replace('\n', ' ')
                    raw_text = re.sub(r'\{.*?\}', '', raw_text)

                    if not stokta_yok_mu:
                        fiyat_eslesmeler = re.findall(
                            r'(?:TL|₺|tl|USD|\$|EUR|€)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl|USD|\$|EUR|€)',
                            raw_text, re.IGNORECASE
                        )
                        gecerli = []
                        for e in fiyat_eslesmeler:
                            sayi = metni_sayiya_cevir(e)
                            if sayi and sayi > 0:
                                gecerli.append((sayi, e))

                        if gecerli:
                            gecerli.sort(key=lambda x: x[0])
                            _, en_uygun_metin = gecerli[0]
                            saf_metin = en_uygun_metin.upper()
                            
                            if "$" in saf_metin or "USD" in saf_metin:
                                fiyat_gosterim = f"{gecerli[0][0]:.2f} $"
                            elif "€" in saf_metin or "EUR" in saf_metin:
                                fiyat_gosterim = f"{gecerli[0][0]:.2f} €"
                            else:
                                fiyat_gosterim = f"{gecerli[0][0]:.2f} TL"
                                
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
                        "tedarikci": ad,
                        "Tedarikci": ad,
                        "urun_adi": isim,
                        "Urun": isim,
                        "fiyat_metni": fiyat_gosterim,
                        "Fiyat": fiyat_gosterim,
                        "canli": (stok_durum == "Canlı Veri"),
                        "Durum": stok_durum,
                        "url": link,
                        "Link": link
                    })
                    sayac += 1
                except Exception:
                    continue
    except Exception as e:
        print(f"[{ad}] HATA: {str(e)}")

    return bulunanlar

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

@app.get("/arama")
def arama_yap(q: str, kategori: str = "Hepsi"):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)
    kategori_kucuk = kategori.lower()

    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
        gelecek_sonuclar = []
        for ad, ayarlar in TEDARIKCILER.items():
            site_kategori = ayarlar["kategori"].lower()
            
            if kategori_kucuk != "hepsi":
                if site_kategori not in kategori_kucuk and kategori_kucuk not in site_kategori:
                    continue

            gelecek_sonuclar.append(executor.submit(site_tara, ad, ayarlar, q_encoded))
            
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
    return {"sonuclar": sonuclar}
