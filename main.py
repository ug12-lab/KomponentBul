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

# Kutu seçicilerini akıllı ve esnek hale getirdik
TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        # .box kaldırıldı, sadece gerçek ürün sınıfı olan .ems-prd bırakıldı
        "seciciler": {"kutu": ".ems-prd, div[class*='product-item']"} 
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-wrapper"}
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        # Motorobit sınıf değiştirdiği için adında product geçen tüm kutuları tarayacağız
        "seciciler": {"kutu": ".showcase, div[class*='product'], li[class*='product']"} 
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box"}
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
    
    try:
        # Engelleri aşan sihirli kalkanımız
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            eklenen_isimler = set()
            
            for urun in urunler:
                if len(bulunanlar) >= 5:
                    break
                    
                try:
                    isim = ""
                    link = url
                    
                    # 1. İSİM BULUCU (A etiketlerini tara, en uzun ve anlamlı metni al)
                    for a in urun.find_all('a'):
                        text = a.text.replace("Yeni", "").replace("YENİ", "").strip()
                        text = re.sub(r'\{.*?\}', '', text) # Vue/React hata kodlarını sil
                        
                        # İncele/Sepete Ekle butonlarını isim olarak alma
                        if len(text) > len(isim) and "incele" not in text.lower() and "sepete ekle" not in text.lower():
                            isim = text
                            temp_link = a.get('href', '')
                            if temp_link:
                                link = temp_link
                                
                    isim = re.sub(r'\s+', ' ', isim).strip()
                    
                    # Çok kısa, anlamsız isimleri ve aynı ürünün kopyalarını pas geç
                    if len(isim) < 5 or isim in eklenen_isimler:
                        continue
                        
                    if link and not link.startswith('http'):
                        link = ayarlar["base_url"] + link if link.startswith('/') else ayarlar["base_url"] + '/' + link

                    # 2. FİYAT VE STOK BULUCU
                    raw_text = urun.text.replace('\n', ' ')
                    raw_text = re.sub(r'\{.*?\}', '', raw_text) # Kırık HTML kodlarını temizle
                    kart_kucuk = raw_text.lower()
                    
                    fiyat_gosterim = "Stokta Yok"
                    stok_durum = "Stokta Yok"
                    
                    # Açıkça tükendi yazmıyorsa fiyat ara
                    if "tükendi" not in kart_kucuk and "stokta yok" not in kart_kucuk:
                        # 15.50 TL, 1.250 TL, 45 ₺ gibi formatları doğrudan arar
                        fiyat_eslesme = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)', raw_text, re.IGNORECASE)
                        
                        if fiyat_eslesme:
                            fiyat_gosterim = fiyat_eslesme.group(0).upper().replace('₺', ' TL').strip()
                            if "TL" not in fiyat_gosterim: 
                                fiyat_gosterim += " TL"
                            stok_durum = "Canlı Veri"
                        else:
                            # Yanında TL yazmıyorsa bile küsuratlı bir sayı varsa (örn: 24,75) kabul et
                            alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', raw_text)
                            if alternatif_sayi and "0,00" not in alternatif_sayi.group(0):
                                fiyat_gosterim = alternatif_sayi.group(0) + " TL"
                                stok_durum = "Canlı Veri"

                    # DİKKAT: Kutu içinde ne fiyat ne de "Tükendi" yazısı yoksa bu bir "Kategori Menüsü"dür (Çöpe at!)
                    if stok_durum == "Stokta Yok" and "tükendi" not in kart_kucuk and "stokta yok" not in kart_kucuk:
                        continue
                        
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
    return {"sonuclar": sonuclar}from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import urllib.parse
import concurrent.futures
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
    "Elektromarketim": {"url": "https://www.elektromarketim.com/arama?q={}", "kutu": ".ems-prd, .product-item, .box"},
    "Robotistan": {"url": "https://www.robotistan.com/arama?q={}", "kutu": ".product-item, .product-wrapper, .general-box"},
    "Motorobit": {"url": "https://www.motorobit.com/arama?q={}", "kutu": ".showcase, .product-item, .col-item"},
    "Robolink": {"url": "https://www.robolinkmarket.com/arama?q={}", "kutu": ".product-item, .product-box"}
}

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url"].format(q_encoded)
    
    try:
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(ayarlar["kutu"])
            
            if urunler:
                # KUTU BULUNDUYSA: İlk ürünün outerHTML'ini (ilk 300 karakterini) ekrana bas!
                raw_html = str(urunler[0]).replace('\n', ' ')[:300] 
                bulunanlar.append({
                    "Tedarikci": ad,
                    "Kategori": "BAŞARILI",
                    "Urun": f"HTML KODU: {raw_html}...",
                    "Fiyat": "200 OK",
                    "Durum": f"{len(urunler)} Kutu Bulundu",
                    "Link": url
                })
            else:
                # SAYFA AÇILDI AMA KUTU YOKSA: Sitenin body kısmını bas!
                body_html = str(soup.body)[:300].replace('\n', ' ') if soup.body else "Body boş"
                bulunanlar.append({
                    "Tedarikci": ad,
                    "Kategori": "KUTU BULUNAMADI",
                    "Urun": f"HTML GÖVDESİ: {body_html}...",
                    "Fiyat": "200 OK",
                    "Durum": "Yanlış Seçici",
                    "Link": url
                })
        else:
            # SİTE BİZİ ENGELLİYORSA (403/404)
            bulunanlar.append({
                "Tedarikci": ad,
                "Kategori": "ENGEL",
                "Urun": f"SUNUCU BİZİ BANLADI. Dönen Kod: {res.status_code}",
                "Fiyat": "YASAK",
                "Durum": "Engellendi",
                "Link": url
            })
    except Exception as e:
        # KOD ÇÖKÜYORSAV VEYA ZAMAN AŞIMI
        bulunanlar.append({
            "Tedarikci": ad,
            "Kategori": "ÇÖKME",
            "Urun": f"Bağlantı Hatası: {str(e)}",
            "Fiyat": "HATA",
            "Durum": "Zaman Aşımı",
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

    # Fiyata göre sıralamayı kapattık ki hata mesajları kaybolmasın
    return {"sonuclar": sonuclar}
