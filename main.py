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

TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".ems-prd, .product-item, div[class*='product']",
            "isim": ".ems-prd-name, .product-name",
            "fiyat": ".ems-prd-price-selling, .product-price, .price"
        } 
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper",
            "isim": ".product-name a, .product-name",
            "fiyat": ".product-price, .current-price, .price"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, div[class*='product'], li[class*='product']",
            "isim": ".showcase-title a, .product-name",
            "fiyat": ".showcase-price-new, .product-price, .price"
        } 
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box",
            "isim": ".product-title a, .product-name",
            "fiyat": ".product-price, .current-price, .price"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Tükendi" in fiyat_str or "Stokta" in fiyat_str:
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
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            eklenen_isimler = set()
            sayac = 0
            
            for urun in urunler:
                if sayac >= 5:
                    break
                    
                try:
                    # 1. İSİM BULUCU
                    isim = ""
                    link = url
                    
                    for a in urun.find_all('a'):
                        text = a.text.replace("Yeni", "").replace("YENİ", "").strip()
                        text = re.sub(r'\{.*?\}', '', text)
                        
                        if len(text) > len(isim) and "incele" not in text.lower() and "sepete ekle" not in text.lower():
                            isim = text
                            temp_link = a.get('href', '')
                            if temp_link:
                                link = temp_link
                                
                    isim = re.sub(r'\s+', ' ', isim).strip()
                    if len(isim) < 5 or isim in eklenen_isimler:
                        continue
                        
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link if link.startswith('/') else ayarlar["base_url"] + '/' + link

                    # 2. HASSAS VE KESİN STOK KONTROLÜ (Girdiğin outerHTML'e göre tasarlandı)
                    stok_yok_mu = False
                    
                    # A. Robolink tarzı gizli stok inputunu kontrol et (value="0" ise kesin tükenmiştir)
                    stok_input = urun.select_one('input[id*="stock-status"], input[name*="stock"]')
                    if stok_input:
                        val = stok_input.get('value', '1')
                        if val == '0':
                            stok_yok_mu = True
                    
                    # B. Tükendi alanı d-none (görünmez) değilse gerçekten tükenmiştir
                    tukendi_div = urun.select_one('.out-stock-available, .out-of-stock, .tukendi')
                    if tukendi_div:
                        siniflar = tukendi_div.get('class', [])
                        if 'd-none' not in siniflar:
                            stok_yok_mu = True

                    fiyat_gosterim = "Tükendi"
                    stok_durum = "Tükendi"
                    
                    # 3. FİYAT BULUCU
                    if not stok_yok_mu:
                        fiyat_etiketi = urun.select_one(sec["fiyat"])
                        if fiyat_etiketi:
                            fiyat_metni = fiyat_etiketi.text.replace('\n', ' ').strip()
                            f_match = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', fiyat_metni)
                            if f_match:
                                temiz_fiyat = f_match.group(0)
                                if "0,00" not in temiz_fiyat and "0.00" not in temiz_fiyat:
                                    fiyat_gosterim = f"{temiz_fiyat} TL"
                                    stok_durum = "Canlı Veri"
                        
                        # Alternatif olarak genel metinden yakala
                        if stok_durum == "Tükendi":
                            raw_text = urun.text.replace('\n', ' ')
                            raw_text = re.sub(r'\{.*?\}', '', raw_text)
                            genel_fiyat = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', raw_text, re.IGNORECASE)
                            if genel_fiyat:
                                f_temiz = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', genel_fiyat.group(0))
                                if f_temiz and "0,00" not in f_temiz.group(0):
                                    fiyat_gosterim = f"{f_temiz.group(0)} TL"
                                    stok_durum = "Canlı Veri"

                    # 4. ÇÖP FİLTRESİ
                    if not stok_yok_mu and stok_durum == "Tükendi":
                        continue

                    eklenen_isimler.add(isim)
                    bulunanlar.append({
                        "Tedarikci": ad,
                        "Kategori": ayarlar["kategori"],
                        "Urun": isim,
                        "Fiyat": fiyat_gosterim,
                        "Durum": stok_durum,
                        "Link": link
                    })
                    sayac += 1
                except Exception:
                    continue
    except Exception as e:
        print(f"[{ad}] HATA: {str(e)}")
        
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
