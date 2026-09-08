from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kutu seçicilerini genişlettik, isim ve fiyat bulma işini Regex'e devrettik
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .box, .ems-prd, div[class*='product']"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper, div[class*='product']"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item, .col-md-3, div[class*='product']"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box, div[class*='product']"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Stokta Yok" in fiyat_str or "HATA" in fiyat_str:
        return 999999.0
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c == ',' or c == '.')
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except:
        return 999999.0

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url_sablonu"].format(q_encoded)
    sec = ayarlar["seciciler"]
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    try:
        res = scraper.get(url, timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:5]:
                try:
                    # 1. AKILLI İSİM BULUCU: Kutu içindeki en uzun metne sahip linki ürün adı kabul et
                    isim = ""
                    link = url # Varsayılan olarak arama sayfasına gitsin
                    en_uzun_metin_uzunlugu = 0
                    
                    for a_etiketi in urun.find_all('a'):
                        metin = a_etiketi.text.replace("Yeni", "").replace("YENİ", "").replace("Sepete Ekle", "").strip()
                        if len(metin) > en_uzun_metin_uzunlugu:
                            en_uzun_metin_uzunlugu = len(metin)
                            isim = metin
                            temp_link = a_etiketi.get('href', '')
                            if temp_link:
                                link = temp_link if temp_link.startswith('http') else "https://www." + ad.lower() + (".com" if ad != "Robolink" else "market.com") + temp_link
                    
                    if len(isim) < 4:
                        continue # Eğer anlamlı bir isim bulamadıysa bu kutuyu atla

                    # 2. AKILLI FİYAT BULUCU: Kutunun içindeki tüm metni tarayıp para birimi formatını yakala
                    kart_metni = urun.text.replace('\n', ' ').strip()
                    fiyat_gosterim = "Stokta Yok"
                    stok_durum = "Stokta Yok"
                    
                    kart_metni_kucuk = kart_metni.lower()
                    if "tükendi" not in kart_metni_kucuk and "stokta yok" not in kart_metni_kucuk:
                        # Örnek: 1.250,00 TL, 15,50 TL, 45 TL veya ₺ simgeli olanları bul
                        fiyat_eslesme = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', kart_metni, re.IGNORECASE)
                        
                        if fiyat_eslesme:
                            fiyat_gosterim = fiyat_eslesme.group(0).upper().replace('₺', 'TL')
                            if "TL" not in fiyat_gosterim:
                                fiyat_gosterim += " TL"
                            stok_durum = "Canlı Veri"
                        else:
                            # Sadece rakam bulmayı dene (TL yazmıyorsa)
                            alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', kart_metni)
                            if alternatif_sayi:
                                fiyat_gosterim = f"{alternatif_sayi.group(0)} TL"
                                stok_durum = "Canlı Veri"

                    bulunanlar.append({
                        "Tedarikci": ad,
                        "Kategori": ayarlar["kategori"],
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"[{ad}] Hata: {str(e)}")
        
    return bulunanlar

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            sonuclar.extend(gelecek.result())

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
