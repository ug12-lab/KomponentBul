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

# SADECE ÇALIŞAN 4 SİTE
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
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
    if not fiyat_str or "Hata" in fiyat_str or "BULUNAMADI" in fiyat_str:
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
            
            # Eğer sitede ürün kutusu hiç bulunamazsa bunu arayüze bas
            if not urunler:
                bulunanlar.append({
                    "Tedarikci": ad,
                    "Kategori": "HATA",
                    "Urun": "Sayfa yüklendi ama HTML ürün kutusu (kutu seçici) bulunamadı!",
                    "Fiyat": "HATA",
                    "Durum": "Kutu Yok",
                    "Link": url
                })
                return bulunanlar
            
            for urun in urunler[:5]:
                isim_etiketi = urun.select_one(sec["isim"])
                fiyat_etiketi = urun.select_one(sec["fiyat"])
                stok_etiketi = urun.select_one(sec["stok"]) if sec.get("stok") else None
                
                # HTML'den çektiği ham metinleri olduğu gibi alıyoruz
                isim = isim_etiketi.text.replace("Yeni", "").strip() if isim_etiketi else "İSİM_BULUNAMADI"
                ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else "FİYAT_BULUNAMADI"
                
                stok_durum = "Veri Çekildi"
                if stok_etiketi:
                    stok_durum = "STOK ETİKETİ VAR"
                elif "FİYAT_BULUNAMADI" in ham_fiyat:
                    stok_durum = "Fiyat Sınıfı Yanlış"
                    
                bulunanlar.append({
                    "Tedarikci": ad,
                    "Kategori": ayarlar["kategori"],
                    "Urun": isim,
                    "Fiyat": ham_fiyat, # Hiçbir filtreleme olmadan direkt fiyatı ekrana basıyoruz
                    "Durum": stok_durum,
                    "Link": url
                })
        else:
            # 403 veya 404 yenirse bunu doğrudan listeye ekle
            bulunanlar.append({
                "Tedarikci": ad,
                "Kategori": "HATA",
                "Urun": f"HTTP {res.status_code} - Site engelledi",
                "Fiyat": "HATA",
                "Durum": "Engellendi",
                "Link": url
            })
    except Exception as e:
        # Kod çökerse hatayı arayüze yazdır
        bulunanlar.append({
            "Tedarikci": ad,
            "Kategori": "HATA",
            "Urun": f"Sistem Çöktü: {str(e)}",
            "Fiyat": "HATA",
            "Durum": "Hata",
            "Link": url
        })
        
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
