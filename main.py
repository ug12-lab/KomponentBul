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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# NOKTA ATIŞI SEÇİCİLER VE STOK ETİKETLERİ
# ==========================================
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .fl.col-12, li.col-3, .box",
            "isim": ".product-name, .product-title",
            "fiyat": ".product-price, .price",
            "stok_class": ".tanitim-stock-alert"
        }
    },
    "Direnc.net": { 
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-box, .product-item",
            "isim": ".product-name a, .title",
            "fiyat": ".product-price, .current-price",
            "stok_class": ".out-of-stock"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper",
            "isim": ".product-name a, .product-name", # Doğrudan link metnini al (Yeni rozetini es geç)
            "fiyat": ".product-price, .current-price",
            "stok_class": ".out-of-stock, .stock-out"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item",
            "isim": ".showcase-title a, .product-name",
            "fiyat": ".showcase-price-new, .product-price",
            "stok_class": ".out-of-stock"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title a, .product-name",
            "fiyat": ".current-price, .product-price",
            "stok_class": ".out-of-stock"
        }
    },
    "Ozdisan": { 
        "url_sablonu": "https://www.ozdisan.com/Search?Word={}",
        "base_url": "https://www.ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {
            "kutu": ".product-item, .product-card, .list-item",
            "isim": ".product-name, .product-title",
            "fiyat": ".price, .wholesale-price",
            "stok_class": ".no-stock"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if "Stokta Yok" in fiyat_str or not fiyat_str:
        return 999999.0
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c == '.' or c == ',')
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except:
        return 999999.0

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url_sablonu"].format(q_encoded)
    sec = ayarlar["seciciler"]
    
    try:
        res = tls_requests.get(url, impersonate="chrome110", timeout=20) # Siteler geç yanıt veriyorsa diye süreyi 20 saniyeye çıkardık
        print(f"[{ad}] HTTP Durum: {res.status_code} | Link: {url}")
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:5]:
                try:
                    isim_etiketi = urun.select_one(sec["isim"])
                    link_etiketi = urun.select_one('a')
                    fiyat_etiketi = urun.select_one(sec["fiyat"])
                    stok_etiketi = urun.select_one(sec["stok_class"]) if sec.get("stok_class") else None
                    
                    if isim_etiketi and link_etiketi:
                        # İsim temizliği (Yeni rozetlerini ve boşlukları sil)
                        isim = isim_etiketi.text.replace("Yeni", "").replace("YENİ", "").strip()
                        if len(isim) < 4: 
                            continue
                            
                        link = link_etiketi.get('href')
                        if link and not link.startswith('http'):
                            link = ayarlar["base_url"] + link
                            
                        ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                        
                        # Artık tüm metni değil, sadece belirlediğimiz HTML etiketlerini ve fiyattaki 0 değerini kontrol ediyoruz
                        if stok_etiketi or not ham_fiyat or "0,00" in ham_fiyat:
                            fiyat_gosterim = "Stokta Yok"
                            stok_durum = "Stokta Yok"
                        else:
                            fiyat_gosterim = f"{ham_fiyat}" if "TL" in ham_fiyat else f"{ham_fiyat} TL"
                            stok_durum = "Canlı Veri"
                        
                        bulunanlar.append({
                            "Tedarikci": ad,
                            "Kategori": ayarlar["kategori"],
                            "Urun": isim,
                            "Fiyat": fiyat_gosterim,
                            "Durum": stok_durum,
                            "Link": link
                        })
                except Exception as ic_hata:
                    continue
    except Exception as e:
        print(f"[{ad}] Bağlantı Koptu veya Engellendi: {str(e)}")
        
    return bulunanlar

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            try:
                sonuclar.extend(gelecek.result())
            except Exception as e:
                print("Eşzamanlı İşlem Hatası:", e)

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
