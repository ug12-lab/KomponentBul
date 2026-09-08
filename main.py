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
# KATI HTML SEÇİCİLERİ (GİZLİ CSS TUZAĞINDAN ARINDIRILMIŞ)
# ==========================================
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .box",
            "isim": ".product-name, .product-title",
            "fiyat": ".product-price",
            "stok_class": ".tanitim-stock-alert" 
        }
    },
    "Direnc.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-box, .product-item",
            "isim": ".product-name, .title",
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
            "isim": ".product-name",
            "fiyat": ".product-price, .current-price",
            "stok_class": ".out-of-stock"
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
            "isim": ".product-title, .product-name",
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
            "isim": ".product-name, .product-title, h2, a",
            "fiyat": ".price, .wholesale-price, .product-price",
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
    
    # Anti-bot sistemlerini tetiklememek için standart tarayıcı başlıkları
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    try:
        res = bireysel_scraper.get(url, headers=headers, timeout=15)
        print(f"{ad} Status: {res.status_code}") # Log takibi için
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:4]:
                try: # Her ürün için ayrı try-except: Biri patlarsa diğerleri çalışsın
                    isim_etiketi = urun.select_one(sec["isim"])
                    link_etiketi = urun.select_one('a')
                    fiyat_etiketi = urun.select_one(sec["fiyat"])
                    
                    # Eğer spesifik stokta yok etiketi tanımlanmışsa ve DOM'da varsa
                    stokta_yok_etiketi = urun.select_one(sec["stok_class"]) if sec.get("stok_class") else None

                    if isim_etiketi and link_etiketi:
                        isim = isim_etiketi.text.strip()
                        link = link_etiketi.get('href')
                        if link and not link.startswith('http'):
                            link = ayarlar["base_url"] + link
                            
                        ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                        sayi_bul = re.search(r'\d+[.,\d]*', ham_fiyat)
                        
                        # KESİN STOK MANTIĞI: Fiyat numarası yoksa veya bariz stokta yok class'ı varsa
                        if not sayi_bul or stokta_yok_etiketi or "0,00" in ham_fiyat:
                            fiyat_gosterim = "Stokta Yok"
                            stok_durum = "Stokta Yok"
                        else:
                            fiyat_gosterim = f"{sayi_bul.group(0)} TL"
                            stok_durum = "Canlı Veri"
                        
                        bulunanlar.append({
                            "Tedarikci": ad,
                            "Kategori": ayarlar["kategori"],
                            "Urun": isim,
                            "Fiyat": fiyat_gosterim,
                            "Durum": stok_durum,
                            "Link": link
                        })
                except Exception as e:
                    continue # Ürün bazlı hataları yoksay, sonrakine geç
                    
    except Exception as e:
        print(f"{ad} Bağlantı Hatası:", str(e))
        
    return bulunanlar

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    # Threadpool ile maksimum paralellik
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            try:
                sonuclar.extend(gelecek.result())
            except Exception as e:
                print("Eşzamanlı işlem hatası:", e)

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
