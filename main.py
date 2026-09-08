from fastapi import FastAPI
from fastapi.responses import FileResponse
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
