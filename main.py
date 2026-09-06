from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gerçek bir tarayıcı gibi görünmek için gelişmiş Cloudscraper ayarları
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True,
        'mobile': False
    }
)

# İstek atarken eklenecek özel tarayıcı kimlikleri (Headers)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    # 1. ELEKTROMARKETİM
    try:
        url_elk = f"https://www.elektromarketim.com/arama?q={q_encoded}"
        res_elk = scraper.get(url_elk, headers=HEADERS, timeout=10)
        
        if res_elk.status_code == 200:
            soup_elk = BeautifulSoup(res_elk.text, 'html.parser')
            # Elektromarketim'in güncel ürün liste elemanları
            urunler = soup_elk.select('.product-item, .fl.col-12.text-center, li.col-3')
            
            for urun in urunler[:3]:
                isim_isim = urun.select_one('.product-name, .product-title, a.product-image-link')
                link_isim = urun.select_one('a')
                fiyat_etiketi = urun.select_one('.product-price, span.product-price')
                stok_uyarisi = urun.select_one('.tanitim-stock-alert')
                
                if isim_isim and link_isim:
                    isim = isim_isim.text.strip()
                    link = link_isim.get('href')
                    if link and not link.startswith('http'):
                        link = "https://www.elektromarketim.com" + link
                    
                    ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else "0,00"
                    if "0,00" in ham_fiyat or stok_uyarisi or not ham_fiyat:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_gosterim = f"{ham_fiyat} TL"
                        stok_durum = "Canlı Veri"
                    
                    sonuclar.append({
                        "Tedarikci": "Elektromarketim",
                        "Urun": isim if isim else "Elektronik Parça",
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
    except Exception as e:
        print("Elektromarketim Hata:", str(e))

    # 2. DİRENC.NET
    try:
        url_dir = f"https://www.direnc.net/arama?q={q_encoded}"
        res_dir = scraper.get(url_dir, headers=HEADERS, timeout=10)
        
        if res_dir.status_code == 200:
            soup_dir = BeautifulSoup(res_dir.text, 'html.parser')
            urunler = soup_dir.select('.product-box, .urun-item, .col-product') 
            
            for urun in urunler[:3]:
                isim_isim = urun.select_one('.product-name, .title')
                link_isim = urun.select_one('a')
                fiyat_isim = urun.select_one('.product-price, .current-price')
                
                if isim_isim and link_isim:
                    isim = isim_isim.text.strip()
                    link = link_isim.get('href')
                    if link and not link.startswith('http'):
                        link = "https://www.direnc.net" + link
                        
                    ham_fiyat = fiyat_isim.text.strip() if fiyat_isim else "0,00"
                    if "0,00" in ham_fiyat or not ham_fiyat:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_gosterim = ham_fiyat
                        stok_durum = "Canlı Veri"
                    
                    sonuclar.append({
                        "Tedarikci": "Direnc.net",
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
    except Exception as e:
        print("Direnc.net Hata:", str(e))

    # 3. ROBOTİSTAN
    try:
        url_rob = f"https://www.robotistan.com/arama?q={q_encoded}"
        res_rob = scraper.get(url_rob, headers=HEADERS, timeout=10)
        
        if res_rob.status_code == 200:
            soup_rob = BeautifulSoup(res_rob.text, 'html.parser')
            urunler = soup_rob.select('.product-item, .col-md-3, .product-wrapper') 
            
            for urun in urunler[:3]:
                isim_isim = urun.select_one('.product-name, .detail h2')
                link_isim = urun.select_one('a')
                fiyat_isim = urun.select_one('.product-price, .current-price')
                
                if isim_isim and link_isim:
                    isim = isim_isim.text.strip()
                    link = link_isim.get('href')
                    if link and not link.startswith('http'):
                        link = "https://www.robotistan.com" + link
                    
                    ham_fiyat = fiyat_isim.text.strip() if fiyat_isim else "0,00"
                    if "0,00" in ham_fiyat or not ham_fiyat:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_gosterim = ham_fiyat
                        stok_durum = "Canlı Veri"
                    
                    sonuclar.append({
                        "Tedarikci": "Robotistan",
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
    except Exception as e:
        print("Robotistan Hata:", str(e))

    # FİYATA GÖRE SIRALAMA ALGORİTMASI
    def fiyat_temizle(fiyat_str):
        if "Stokta Yok" in fiyat_str:
            return 999999.0
        temiz = ''.join(c for c in fiyat_str if c.isdigit() or c == ',')
        temiz = temiz.replace(',', '.')
        try:
            return float(temiz)
        except:
            return 999999.0

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
