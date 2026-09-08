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

# ==========================================
# AKILLI TEDARİKÇİ VERİTABANI (REVİZE EDİLDİ)
# ==========================================
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .box",
            "isim": ".product-name, .product-title",
            "fiyat": ".product-price"
        }
    },
    "Direnc.net": {
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
            "kutu": ".product-item, .product-wrapper",
            "isim": ".product-name",
            "fiyat": ".product-price, .current-price"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item",
            "isim": ".showcase-title a, .product-name",
            "fiyat": ".showcase-price-new, .product-price"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title, .product-name",
            "fiyat": ".current-price, .product-price"
        }
    },
    "Ozdisan": {
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
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c == ',')
    temiz = temiz.replace(',', '.')
    try:
        return float(temiz)
    except:
        return 999999.0

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url_sablonu"].format(q_encoded)
    sec = ayarlar["seciciler"]
    
    bireysel_scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    try:
        res = bireysel_scraper.get(url, headers=headers, timeout=12)
        print(f"{ad} Status: {res.status_code}") 
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            # Daha fazla sonuç yakalamak için limiti 4'e çıkardık
            for urun in urunler[:4]:  
                isim_etiketi = urun.select_one(sec["isim"])
                link_etiketi = urun.select_one('a')
                fiyat_etiketi = urun.select_one(sec["fiyat"])
                
                if isim_etiketi and link_etiketi:
                    isim = isim_etiketi.text.strip()
                    link = link_etiketi.get('href')
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link
                        
                    # 1. BÜTÜNCÜL METİN STOK KONTROLÜ (CSS tuzağından kaçış)
                    kart_metni = urun.text.lower()
                    if "tükendi" in kart_metni or "stokta yok" in kart_metni or "gelince haber ver" in kart_metni:
                        stok_durum = "Stokta Yok"
                    else:
                        stok_durum = "Canlı Veri"

                    # 2. REGEX İLE KESİN FİYAT AYIKLAMA (Sıfırları ve hataları yoksayma)
                    ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                    sayi_bul = re.search(r'\d+[.,\d]*', ham_fiyat)
                    
                    if sayi_bul and stok_durum != "Stokta Yok":
                        fiyat_gosterim = f"{sayi_bul.group(0)} TL"
                    else:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    
                    bulunanlar.append({
                        "Tedarikci": ad,
                        "Kategori": ayarlar["kategori"],
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
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
            sonuclar.extend(gelecek.result())

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
