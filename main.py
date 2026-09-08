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
# ÇALIŞAN 4 SİTE - KESİN HTML SEÇİCİLERİ
# ==========================================
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .box",
            "isim": ".product-name, .product-title",
            "fiyat": ".product-price, .price",
            "stok": ".tanitim-stock-alert"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper",
            "isim": ".product-name a, .product-name",
            "fiyat": ".product-price, .current-price, .price",
            "stok": ".out-of-stock, .stock-out"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item",
            "isim": ".showcase-title a, .product-name",
            "fiyat": ".showcase-price-new, .product-price, .price",
            "stok": ".out-of-stock"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title a, .product-name",
            "fiyat": ".current-price, .product-price, .price",
            "stok": ".out-of-stock"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if "Stokta Yok" in fiyat_str or not fiyat_str:
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
    
    try:
        # Cloudflare ve bot korumalarını "chrome110" maskesiyle aşıyoruz
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)
        print(f"[{ad}] HTTP Durum: {res.status_code}") # Loglarda artık ne döndüğünü kesin göreceğiz
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:5]:
                try:
                    isim_etiketi = urun.select_one(sec["isim"])
                    link_etiketi = urun.select_one('a')
                    
                    if not isim_etiketi or not link_etiketi:
                        continue
                        
                    isim = isim_etiketi.text.replace("Yeni", "").replace("YENİ", "").strip()
                    if len(isim) < 3:
                        continue
                        
                    link = link_etiketi.get('href')
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link
                        
                    # --- FİYAT VE STOK KONTROLÜ (YENİ MANTIK) ---
                    fiyat_etiketi = urun.select_one(sec["fiyat"])
                    ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                    
                    stok_yok_mu = False
                    if sec.get("stok"):
                        stok_etiketi = urun.select_one(sec["stok"])
                        if stok_etiketi:
                            stok_yok_mu = True
                            
                    # Sadece rakamları yakala (150,00 veya 1.500)
                    fiyat_eslesme = re.search(r'\d+[.,\d]*', ham_fiyat)
                    
                    if stok_yok_mu or not fiyat_eslesme or "0,00" in ham_fiyat:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_gosterim = fiyat_eslesme.group(0) + " TL"
                        stok_durum = "Canlı Veri"
                    
                    bulunanlar.append({
                        "Tedarikci": ad,
                        "Kategori": ayarlar["kategori"],
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
                except Exception as inner_e:
                    continue
    except Exception as e:
        print(f"[{ad}] Bağlantı Hatası: {str(e)}")
        
    return bulunanlar

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            try:
                sonuclar.extend(gelecek.result())
            except Exception as e:
                print("Eşzamanlı işlem hatası:", e)

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
