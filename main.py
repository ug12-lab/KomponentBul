from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# MERKEZİ TEDARİKÇİ VERİTABANI
# ==========================================
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "ozel_header": None,
        "seciciler": {
            "kutu": ".product-item, .fl.col-12.text-center, li.col-3, .box",
            "isim": ".product-name, .product-title, a",
            "link": "a",
            "fiyat": ".product-price",
            "stok_uyarisi": ".tanitim-stock-alert"
        }
    },
    "Direnc.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "ozel_header": {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'},
        "seciciler": {
            "kutu": ".product-box, .product-item",
            "isim": ".product-name, .title",
            "link": "a",
            "fiyat": ".product-price, .current-price",
            "stok_uyarisi": None
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "ozel_header": None,
        "seciciler": {
            "kutu": ".product-item, .col-md-3, .product-wrapper",
            "isim": ".product-name",
            "link": "a",
            "fiyat": ".product-price",
            "stok_uyarisi": None
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "ozel_header": None,
        "seciciler": {
            "kutu": ".showcase, .product-item",
            "isim": ".showcase-title a, .product-name",
            "link": "a",
            "fiyat": ".showcase-price-new, .product-price",
            "stok_uyarisi": ".out-of-stock"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "ozel_header": None,
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title, .product-name",
            "link": "a",
            "fiyat": ".current-price, .product-price",
            "stok_uyarisi": ".out-of-stock"
        }
    },
    "Ozdisan": {
        "url_sablonu": "https://www.ozdisan.com/Product/Search?searchtext={}",
        "base_url": "https://www.ozdisan.com",
        "kategori": "Toptan",
        "ozel_header": None,
        "seciciler": {
            "kutu": ".product-list-item, .row-item",
            "isim": ".product-name, h2",
            "link": "a",
            "fiyat": ".price, .wholesale-price",
            "stok_uyarisi": ".no-stock"
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
    
    # Çakışmayı önlemek için her siteye özel taze bir scraper oluşturuluyor
    bireysel_scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    # Eğer siteye özel bir header varsa onu, yoksa standart PC kimliğini kullan
    headers = ayarlar.get("ozel_header") or {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        res = bireysel_scraper.get(url, headers=headers, timeout=12)
        print(f"{ad} Status: {res.status_code}") # Hata ayıklama için Render loglarına yaz
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            for urun in urunler[:3]:
                isim_etiketi = urun.select_one(sec["isim"])
                link_etiketi = urun.select_one(sec["link"])
                fiyat_etiketi = urun.select_one(sec["fiyat"])
                stok_uyarisi = urun.select_one(sec["stok_uyarisi"]) if sec.get("stok_uyarisi") else None
                
                if isim_etiketi and link_etiketi:
                    isim = isim_etiketi.text.strip()
                    link = link_etiketi.get('href')
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link
                        
                    ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else "0,00"
                    
                    if "0,00" in ham_fiyat or stok_uyarisi or not ham_fiyat:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_gosterim = f"{ham_fiyat} TL" if "TL" not in ham_fiyat else ham_fiyat
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
        print(f"{ad} Hata:", str(e))
        
    return bulunanlar

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    # Maksimum 6 paralel işlem ile arama
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            sonuclar.extend(gelecek.result())

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
