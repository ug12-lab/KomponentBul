from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures
import re
from curl_cffi import requests as tls_requests # 403'leri yıkan yeni silahımız

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .fl.col-12, li.col-3, .box",
            "isim": ".product-name, .product-title, h2 a, a.product-image-link",
            "fiyat": ".product-price, .price"
        }
    },
    "Direnc.net": { # Artık 403 yemeyecek
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-box, .product-item",
            "isim": ".product-name, .title",
            "fiyat": ".product-price, .current-price"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .col-md-3, .product-wrapper, .general-box",
            "isim": ".product-name, h2, a",
            "fiyat": ".product-price, .current-price, .price"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item, .col-item",
            "isim": ".showcase-title, .product-name, a",
            "fiyat": ".showcase-price-new, .product-price, .price"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box, .col-item",
            "isim": ".product-title, .product-name, h2",
            "fiyat": ".current-price, .product-price, .price"
        }
    },
    "Ozdisan": { # 404 sorununu çözdüğümüz link yapısı
        "url_sablonu": "https://www.ozdisan.com/Search?Word={}",
        "base_url": "https://www.ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {
            "kutu": ".product-item, .product-card, .list-item",
            "isim": ".product-name, .product-title, h2, a",
            "fiyat": ".price, .wholesale-price, .product-price"
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
        # TLS parmak izini "chrome110" olarak simüle ederek anti-bot sistemlerini geçiyoruz
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)
        print(f"{ad} Status: {res.status_code}")
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:5]:
                try:
                    isim_etiketi = urun.select_one(sec["isim"])
                    link_etiketi = urun.select_one('a')
                    fiyat_etiketi = urun.select_one(sec["fiyat"])
                    
                    if isim_etiketi and link_etiketi:
                        isim = isim_etiketi.text.strip()
                        if len(isim) < 2:
                            continue
                            
                        link = link_etiketi.get('href')
                        if link and not link.startswith('http'):
                            link = ayarlar["base_url"] + link
                            
                        ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                        
                        kart_metni = urun.text.lower()
                        if "tükendi" in kart_metni or not ham_fiyat or "0,00" in ham_fiyat:
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
                except Exception:
                    continue
    except Exception as e:
        print(f"{ad} Hata:", str(e))
        
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
                print("Thread hatası:", e)

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
