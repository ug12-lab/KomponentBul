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

# Sadece Kutu Seçicileri (İsim ve fiyatı class'tan değil, akıllı metinden alacağız)
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .box, .ems-prd, .product-card"
        }
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-wrapper, .general-box"
        }
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".showcase, .product-item, .col-item"
        }
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {
            "kutu": ".product-item, .product-box"
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
            
            eklenen_isimler = set() # Aynı ürünün alt alta 4 kere çıkmasını (Robotistan hatası) engeller
            sayac = 0
            
            for urun in urunler:
                if sayac >= 5:
                    break
                    
                try:
                    kart_metni = urun.text.replace('\n', ' ').strip()
                    kart_metni_kucuk = kart_metni.lower()
                    
                    # Vue.js kodlarını ({{ P.price... }}) tamamen imha et (Robolink hatasını çözer)
                    if "{" in kart_metni:
                        kart_metni = re.sub(r'\{.*?\}', '', kart_metni)
                        kart_metni_kucuk = kart_metni.lower()

                    # 1. AKILLI FİYAT VE ÇÖP KUTUSU FİLTRESİ
                    fiyat_eslesme = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', kart_metni, re.IGNORECASE)
                    
                    stokta_yok_mu = "tükendi" in kart_metni_kucuk or "stokta yok" in kart_metni_kucuk
                    
                    # Eğer kutuda fiyat formatı YOKSA ve Tükendi de YAZMIYORSA, bu bir sol menü/kategoridir (Elektromarketim Hatası). Pas geç!
                    if not fiyat_eslesme and not stokta_yok_mu:
                        continue
                        
                    # 2. İSİM BULMA (En uzun A etiketindeki yazıyı isim say)
                    isim = ""
                    link = url
                    en_uzun_uzunluk = 0
                    
                    for a_etiketi in urun.find_all('a'):
                        metin = a_etiketi.text.replace("Yeni", "").replace("YENİ", "").strip()
                        if len(metin) > en_uzun_uzunluk and "{" not in metin:
                            en_uzun_uzunluk = len(metin)
                            isim = metin
                            temp_link = a_etiketi.get('href', '')
                            if temp_link:
                                link = temp_link if temp_link.startswith('http') else ayarlar["base_url"] + temp_link

                    # Çöp isimleri veya aynı ürünü tekrar eklemeyi engelle
                    if len(isim) < 5 or isim.upper() in ["SEPETE EKLE", "İNCELE", "DETAY", "STOKTA YOK"]:
                        continue
                    if isim in eklenen_isimler:
                        continue

                    # 3. FİYATI DÜZENLEME
                    fiyat_gosterim = "Stokta Yok"
                    stok_durum = "Stokta Yok"
                    
                    if not stokta_yok_mu:
                        if fiyat_eslesme:
                            fiyat_gosterim = fiyat_eslesme.group(0).upper().replace('₺', 'TL')
                            if "TL" not in fiyat_gosterim:
                                fiyat_gosterim += " TL"
                            stok_durum = "Canlı Veri"
                        else:
                            # Sadece düz rakam varsa (örn: 24,75)
                            alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', kart_metni)
                            if alternatif_sayi:
                                fiyat_gosterim = f"{alternatif_sayi.group(0)} TL"
                                stok_durum = "Canlı Veri"

                    # 0 TL gibi saçma değerleri stokta yok yap
                    if "0,00" in fiyat_gosterim or "0.00" in fiyat_gosterim:
                        fiyat_gosterim = "Stokta Yok"
                        stok_durum = "Stokta Yok"

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
