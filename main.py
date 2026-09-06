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

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

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
        res_elk = scraper.get(url_elk, timeout=10)
        print("Elektromarketim Status:", res_elk.status_code) # Render loglarında göreceğiz
        
        soup_elk = BeautifulSoup(res_elk.text, 'html.parser')
        urunler = soup_elk.select('.fl.col-12.text-center, .product-item, .box')
        
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name, .product-title, a')
            link_isim = urun.select_one('a')
            fiyat_etiketi = urun.select_one('.product-price')
            stok_uyarisi = urun.select_one('.tanitim-stock-alert')
            
            if isim_isim and link_isim and fiyat_etiketi:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if link and not link.startswith('http'):
                    link = "https://www.elektromarketim.com" + link
                
                ham_fiyat = fiyat_etiketi.text.strip()
                if "0,00" in ham_fiyat or stok_uyarisi:
                    fiyat_gosterim = "Stokta Yok"
                    stok_durum = "Stokta Yok"
                else:
                    fiyat_gosterim = f"{ham_fiyat} TL"
                    stok_durum = "Canlı Veri"
                
                sonuclar.append({
                    "Tedarikci": "Elektromarketim",
                    "Urun": isim,
                    "Fiyat": fiyat_gosterim,
                    "Durum": stok_durum,
                    "Link": link
                })
    except Exception as e:
        print("Elektromarketim Hata:", str(e))

    # 2. DİRENC.NET
    try:
        url_dir = f"https://www.direnc.net/arama?q={q_encoded}"
        res_dir = scraper.get(url_dir, timeout=10)
        print("Direnc.net Status:", res_dir.status_code)
        
        soup_dir = BeautifulSoup(res_dir.text, 'html.parser')
        urunler = soup_dir.select('.product-box, .product-item') 
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name')
            link_isim = urun.select_one('a')
            fiyat_isim = urun.select_one('.product-price')
            
            if isim_isim and link_isim and fiyat_isim:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if link and not link.startswith('http'):
                    link = "https://www.direnc.net" + link
                    
                ham_fiyat = fiyat_isim.text.strip()
                if "0,00" in ham_fiyat:
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
        res_rob = scraper.get(url_rob, timeout=10)
        print("Robotistan Status:", res_rob.status_code)
        
        soup_rob = BeautifulSoup(res_rob.text, 'html.parser')
        urunler = soup_rob.select('.product-item, .col-md-3') 
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name')
            link_isim = urun.select_one('a')
            fiyat_isim = urun.select_one('.product-price')
            
            if isim_isim and link_isim and fiyat_isim:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if link and not link.startswith('http'):
                    link = "https://www.robotistan.com" + link
                
                ham_fiyat = fiyat_isim.text.strip()
                if "0,00" in ham_fiyat:
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

    # SIRALAMA
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
