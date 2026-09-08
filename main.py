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

# SEÇİCİLER (Hem esnek hem güvenli genişlikte)
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".ems-prd, .product-item, .box",
            "isim": ".ems-prd-name, .product-name",
            "fiyat": ".ems-prd-price-selling, .product-price, .price"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper, .general-box",
            "isim": ".product-name a, .product-name",
            "fiyat": ".product-price, .current-price, .price"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item, .col-item",
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
            "fiyat": ".current-price, .product-price, .price"
        }
    }
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Stokta Yok" in fiyat_str:
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
            
            eklenen_isimler = set() # Robotistan klon engelliyici
            sayac = 0
            
            for urun in urunler:
                if sayac >= 5:
                    break
                    
                try:
                    # 1. KART METNİ TEMİZLİĞİ (Robolink Vue kodlarını anında yok et)
                    kart_metni = urun.text.replace('\n', ' ')
                    kart_metni_temiz = re.sub(r'\{.*?\}', '', kart_metni).strip()
                    kart_metni_kucuk = kart_metni_temiz.lower()
                    
                    # 2. HİBRİT İSİM BULUCU (Önce sınıf ara, yoksa en uzun A etiketini al)
                    isim = ""
                    link = url
                    isim_etiketi = urun.select_one(sec["isim"])
                    
                    if isim_etiketi:
                        isim = isim_etiketi.text.strip()
                        a_etiketi = isim_etiketi if isim_etiketi.name == 'a' else isim_etiketi.find('a')
                        if not a_etiketi: a_etiketi = urun.find('a')
                        if a_etiketi: link = a_etiketi.get('href', url)
                    else:
                        en_uzun = 0
                        for a in urun.find_all('a'):
                            m = a.text.strip()
                            if len(m) > en_uzun and "{" not in m:
                                en_uzun = len(m)
                                isim = m
                                link = a.get('href', url)
                    
                    # İsim sterilizasyonu
                    isim = isim.replace("Yeni", "").replace("YENİ", "").strip()
                    isim = re.sub(r'\s+', ' ', isim) # Fazla boşlukları tek boşluğa düşür
                    
                    if len(isim) < 5 or isim.upper() in ["SEPETE EKLE", "İNCELE", "DETAY", "STOKTA YOK"]:
                        continue
                    if "{" in isim or "}" in isim:
                        continue
                    if isim in eklenen_isimler:
                        continue
                        
                    if not link.startswith('http'):
                        link = ayarlar["base_url"] + link if link.startswith('/') else ayarlar["base_url"] + '/' + link
                        
                    # 3. HİBRİT FİYAT VE STOK BULUCU
                    fiyat_gosterim = "Stokta Yok"
                    stok_durum = "Stokta Yok"
                    
                    if "tükendi" in kart_metni_kucuk or "stokta yok" in kart_metni_kucuk:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"
                    else:
                        fiyat_etiketi = urun.select_one(sec["fiyat"])
                        ham_fiyat = fiyat_etiketi.text.strip() if fiyat_etiketi else ""
                        ham_fiyat = re.sub(r'\{.*?\}', '', ham_fiyat).strip()
                        
                        fiyat_bulundu = False
                        
                        # A. Nokta Atışı: Fiyat etiketinden çek
                        if ham_fiyat:
                            f_match = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', ham_fiyat)
                            if f_match and "0,00" not in f_match.group(0):
                                fiyat_gosterim = f_match.group(0) + " TL"
                                stok_durum = "Canlı Veri"
                                fiyat_bulundu = True
                        
                        # B. Kurtarıcı: Etiket değişmişse genel kart metninden çek
                        if not fiyat_bulundu:
                            genel_match = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', kart_metni_temiz, re.IGNORECASE)
                            if genel_match:
                                temiz_r = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', genel_match.group(0))
                                if temiz_r and "0,00" not in temiz_r.group(0):
                                    fiyat_gosterim = temiz_r.group(0) + " TL"
                                    stok_durum = "Canlı Veri"
                                    fiyat_bulundu = True
                                    
                        # C. ÇÖP KUTUSU SİSTEMİ (En Önemli Kısım)
                        # Tükendi yazmıyorsa ve fiyat da bulunamadıysa bu bir ürün değil sol menüdür! Atla.
                        if not fiyat_bulundu:
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
        print(f"[{ad}] Hata: {str(e)}")
        
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
