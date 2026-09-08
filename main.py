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

# KATI VE NET SEÇİCİLER (Kenar çubuklarını ve menüleri dışlar)
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".ems-prd", # Sadece gerçek ürün kartlarını alır
            "isim": ".ems-prd-name, .product-name",
            "fiyat": ".ems-prd-price-selling, .product-price, .price"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item",
            "isim": ".product-name a, .product-name",
            "fiyat": ".product-price, .current-price, .price"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase",
            "isim": ".showcase-title a, .product-name",
            "fiyat": ".showcase-price-new, .product-price, .price"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title a, .product-name",
            "fiyat": ".current-price, .product-price, .price"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Stokta Yok" in fiyat_str:
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
            
            eklenen_isimler = set() # Aynı ürünün alt alta 3 kere çıkmasını engeller
            sayac = 0
            
            for urun in urunler:
                if sayac >= 5:
                    break
                    
                try:
                    isim_etiketi = urun.select_one(sec["isim"])
                    if not isim_etiketi:
                        continue
                        
                    isim = isim_etiketi.text.replace("Yeni", "").replace("YENİ", "").strip()
                    
                    # --- ÇÖP FİLTRESİ ---
                    # Vue.js kodlarını ({{ }}), buton metinlerini ve çok kısa kelimeleri sil
                    if len(isim) < 4 or "{" in isim or "}" in isim:
                        continue
                    if isim.upper() in ["SEPETE EKLE", "İNCELE", "INCELE", "DETAY"]:
                        continue
                    if isim in eklenen_isimler:
                        continue
                    
                    # Link Çekimi
                    link_etiketi = urun.select_one('a')
                    link = link_etiketi.get('href', url) if link_etiketi else url
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link if "base_url" in ayarlar else url
                        
                    # --- NET FİYAT VE STOK BULUCU ---
                    fiyat_etiketi = urun.select_one(sec["fiyat"])
                    ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                    
                    kart_metni = urun.text.lower()
                    
                    if "tükendi" in kart_metni or "stokta yok" in kart_metni:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        # Eğer fiyat etiketinde garip bir kod varsa pas geç
                        if "{" in ham_fiyat or "}" in ham_fiyat:
                            ham_fiyat = ""
                            
                        # Fiyat etiketi içinde geçerli bir sayı ara (örn: 15.50 veya 1.250,00)
                        fiyat_eslesme = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', ham_fiyat)
                        
                        if fiyat_eslesme and "0,00" not in ham_fiyat:
                            fiyat_gosterim = f"{fiyat_eslesme.group(0)} TL"
                            stok_durum = "Canlı Veri"
                        else:
                            # Eğer spesifik etikette bulamazsa, genel ürün kartında "TL" formatında sayı ara
                            fiyat_eslesme_genel = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', urun.text, re.IGNORECASE)
                            if fiyat_eslesme_genel:
                                temiz_rakam = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', fiyat_eslesme_genel.group(0))
                                fiyat_gosterim = f"{temiz_rakam.group(0)} TL" if temiz_rakam else "Stokta Yok"
                                stok_durum = "Canlı Veri" if temiz_rakam else "Stokta Yok"
                            else:
                                fiyat_gosterim = "Stokta Yok"
                                stok_durum = "Stokta Yok"

                    eklenen_isimler.add(isim)
                    bulunanlar.append({
                        "Tedarikci": ad,
                        "Kategori": ayarlar["kategori"],
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
                    sayac += 1
                    
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
