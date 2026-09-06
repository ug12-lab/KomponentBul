from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cloudscraper
from bs4 import BeautifulSoup
import urllib.parse

app = FastAPI()

# Arayüz (taslak.html) ile API'nin haberleşebilmesi için güvenlik izinleri
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bot korumalarını (Cloudflare vb.) aşmak için insan taklidi yapan tarayıcı nesnesi
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

@app.get("/arama")
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    # ==========================================
    # 1. ELEKTROMARKETİM
    # ==========================================
    try:
        url_elk = f"https://www.elektromarketim.com/arama?q={q_encoded}"
        res_elk = scraper.get(url_elk, timeout=10)
        soup_elk = BeautifulSoup(res_elk.text, 'html.parser')
        
        urunler = soup_elk.select('.fl.col-12.text-center, .product-item') # Ürün kartları
        
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name, .product-title, a')
            link_isim = urun.select_one('a')
            fiyat_etiketi = urun.select_one('.product-price')
            stok_uyarisi = urun.select_one('.tanitim-stock-alert') # Gönderdiğin HTML'den alındı
            
            if isim_isim and link_isim and fiyat_etiketi:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if not link.startswith('http'):
                    link = "https://www.elektromarketim.com" + link
                
                ham_fiyat = fiyat_etiketi.text.strip()
                
                # Stok kontrolü (Fiyat 0,00 ise veya Stok uyarısı varsa)
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
    except Exception:
        pass

    # ==========================================
    # 2. DİRENC.NET (Bot engeli aşıldı)
    # ==========================================
    try:
        url_dir = f"https://www.direnc.net/arama?q={q_encoded}"
        res_dir = scraper.get(url_dir, timeout=10)
        soup_dir = BeautifulSoup(res_dir.text, 'html.parser')
        
        urunler = soup_dir.select('.product-box') 
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name')
            link_isim = urun.select_one('a')
            fiyat_isim = urun.select_one('.product-price')
            
            if isim_isim and link_isim and fiyat_isim:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if not link.startswith('http'):
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
    except Exception:
        pass

    # ==========================================
    # 3. ROBOTİSTAN
    # ==========================================
    try:
        url_rob = f"https://www.robotistan.com/arama?q={q_encoded}"
        res_rob = scraper.get(url_rob, timeout=10)
        soup_rob = BeautifulSoup(res_rob.text, 'html.parser')
        
        urunler = soup_rob.select('.product-item, .col-md-3.col-sm-4.col-xs-6') 
        for urun in urunler[:3]:
            isim_isim = urun.select_one('.product-name')
            link_isim = urun.select_one('a')
            fiyat_isim = urun.select_one('.product-price')
            
            if isim_isim and link_isim and fiyat_isim:
                isim = isim_isim.text.strip()
                link = link_isim.get('href')
                if not link.startswith('http'):
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
    except Exception:
        pass

    # ==========================================
    # FİYATA GÖRE SIRALAMA ALGORİTMASI
    # ==========================================
    def fiyat_temizle(fiyat_str):
        if "Stokta Yok" in fiyat_str:
            return 999999.0 # Stokta olmayanları listenin en sonuna at
        
        # Metinden sadece rakamları ve virgülü al
        temiz = ''.join(c for c in fiyat_str if c.isdigit() or c == ',')
        temiz = temiz.replace(',', '.')
        try:
            return float(temiz)
        except:
            return 999999.0

    # Sonuçları en ucuzdan en pahalıya doğru sırala
    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))

    return {"sonuclar": sonuclar}
