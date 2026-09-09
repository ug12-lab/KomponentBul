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
    allow_credentials=False,  
    allow_methods=["*"],
    allow_headers=["*"],
)

TEDARIKCILER = {
    # B2C - Perakende
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".ems-prd"}
    },
    "Robotistan": {
        "url_sablonu": "https://www.robotistan.com/arama?q={}",
        "base_url": "https://www.robotistan.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item"}
    },
    "Motorobit": {
        "url_sablonu": "https://www.motorobit.com/arama?q={}",
        "base_url": "https://www.motorobit.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, .product-item"}
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box"}
    },
    "Direnç.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-list-item"}
    },
    "Komponentci": {
        "url_sablonu": "https://www.komponentci.net/arama?q={}",
        "base_url": "https://www.komponentci.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .showcase"}
    },
    "Samm Market": {
        "url_sablonu": "https://market.samm.com/arama?q={}",
        "base_url": "https://market.samm.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box"}
    },
    # B2B - Toptan
    "Özdisan": {
        "url_sablonu": "https://www.ozdisan.com/Arama?q={}",
        "base_url": "https://www.ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, .list-item"}
    },
    "Merter Elektronik": {
        "url_sablonu": "https://www.merterelektronik.com/arama?q={}",
        "base_url": "https://www.merterelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, .product"}
    }
}

GIZLI_ISARETLERI = {"d-none", "hidden", "invisible", "display-none", "hide"}

def gorunur_mu(etiket):
    for el in [etiket] + list(etiket.parents):
        if not hasattr(el, "get"):
            continue
        siniflar = el.get("class", []) or []
        if any(c in GIZLI_ISARETLERI for c in siniflar):
            return False
        stil = (el.get("style", "") or "").replace(" ", "").lower()
        if "display:none" in stil or "visibility:hidden" in stil:
            return False
        if el.has_attr("hidden"):
            return False
    return True

def fiyat_temizle(fiyat_str):
    if not fiyat_str or "Tükendi" in fiyat_str or "Stokta" in fiyat_str:
        return 999999.0
    temiz = ''.join(c for c in fiyat_str if c.isdigit() or c in ',.')
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except Exception:
        return 999999.0

def metni_sayiya_cevir(fiyat_metni):
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni)
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except Exception:
        return None

def site_tara(ad, ayarlar, q_encoded):
    bulunanlar = []
    url = ayarlar["url_sablonu"].format(q_encoded)
    sec = ayarlar["seciciler"]

    try:
        res = tls_requests.get(url, impersonate="chrome110", timeout=15)

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            urunler = soup.select(sec["kutu"])
            
            is_detail_page = False
            # YÖNLENDİRME AVCISI: Eğer liste kutusu bulamazsa, doğrudan ürün detayına atmıştır. 
            if not urunler:
                body = soup.find('body')
                if body:
                    urunler = [body]
                    is_detail_page = True

            eklenen_isimler = set()
            sayac = 0

            for urun in urunler:
                if sayac >= 5:
                    break

                try:
                    isim = ""
                    link = url

                    # 1. İSİM BULUCU
                    # Yönlendirme varsa (Detay sayfasıysa) en tepe başlığı (H1) al
                    if is_detail_page:
                        h1 = urun.find('h1')
                        if h1:
                            isim = h1.text.replace("Yeni", "").replace("YENİ", "").strip()
                            isim = re.sub(r'\{.*?\}', '', isim).strip()
                            
                    # Liste sayfasındaysak standart A etiketi taramaya devam et
                    if len(isim) < 5:
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

                    # 2. GÖRÜNÜRLÜK-FARKINDA STOK KONTROLÜ
                    stokta_yok_mu = False

                    aday = urun.select_one('.out-of-stock, .stock-out, .no-stock, .tukendi, .sold-out, .ems-prd-badge-tukendi, .product-out-of-stock')
                    if aday and gorunur_mu(aday):
                        stokta_yok_mu = True

                    if not stokta_yok_mu:
                        for etiket in urun.find_all(['div', 'span', 'a', 'p', 'b', 'button']):
                            metin = etiket.text.strip().lower()
                            if metin in ["tükendi", "stokta yok", "tükendi̇"] and gorunur_mu(etiket):
                                stokta_yok_mu = True
                                break

                    fiyat_gosterim = "Tükendi"
                    stok_durum = "Tükendi"

                    # 3. EVRENSEL FİYAT BULUCU (TL, USD, EUR Desteği)
                    raw_text = urun.text.replace('\n', ' ')
                    raw_text = re.sub(r'\{.*?\}', '', raw_text)

                    if not stokta_yok_mu:
                        fiyat_sonda = re.findall(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl|USD|usd|\$|€|EUR)', raw_text, re.IGNORECASE)
                        fiyat_basta = re.findall(r'(?:TL|₺|tl|USD|usd|\$|€|EUR)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?', raw_text, re.IGNORECASE)
                        
                        tum_eslesmeler = fiyat_sonda + fiyat_basta
                        gecerli = []
                        
                        for e in tum_eslesmeler:
                            sayi = metni_sayiya_cevir(e)
                            if sayi and sayi > 0:
                                gecerli.append((sayi, e))

                        if gecerli:
                            tl_olanlar = [g for g in gecerli if "TL" in g[1].upper() or "₺" in g[1]]
                            
                            # Sıralama algoritmasının bozulmaması için TL fiyatı bulursa onu önceliklendirir
                            if tl_olanlar:
                                tl_olanlar.sort(key=lambda x: x[0])
                                _, en_uygun_metin = tl_olanlar[0]
                            else:
                                gecerli.sort(key=lambda x: x[0])
                                _, en_uygun_metin = gecerli[0]
                                
                            fiyat = en_uygun_metin.upper().strip()
                            fiyat = fiyat.replace('₺', ' TL').replace('$', ' USD').replace('€', ' EUR')
                            if not any(curr in fiyat for curr in ["TL", "USD", "EUR"]):
                                fiyat += " TL"
                                
                            fiyat_gosterim = fiyat
                            stok_durum = "Canlı Veri"
                        else:
                            alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', raw_text)
                            if alternatif_sayi:
                                fiyat_gosterim = alternatif_sayi.group(0) + " TL"
                                stok_durum = "Canlı Veri"

                    # 4. ÇÖP FİLTRESİ VE B2B GİZLİ FİYAT KONTROLÜ
                    if not stokta_yok_mu and stok_durum == "Tükendi":
                        # Detay sayfasındaysak ama fiyat okuyamadıysak (Örn: Özdisan Üye Girişi istiyorsa) 
                        # Ürünü gizlemek yerine Fiyat Göster uyarısı veriyoruz. (Boş arama sayfalarını eler)
                        if is_detail_page and len(isim) > 5 and "arama" not in isim.lower() and "bulunamadı" not in raw_text.lower():
                            fiyat_gosterim = "Siteye Git"
                            stok_durum = "Fiyat Gizli"
                        else:
                            continue

                    if "0,00" in fiyat_gosterim or "0.00" in fiyat_gosterim:
                        fiyat_gosterim = "Tükendi"
                        stok_durum = "Tükendi"

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

@app.get("/")
def ana_sayfa():
    return FileResponse("taslak.html")

@app.get("/arama")
def arama_yap(q: str, kategori: str = "Hepsi"):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)
    
    filtrelenmis_siteler = {
        ad: ayarlar for ad, ayarlar in TEDARIKCILER.items()
        if kategori == "Hepsi" or ayarlar["kategori"] == kategori
    }

    # Tarama hızı düşmesin diye işlem kapasitesi 8'e çıkarıldı
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in filtrelenmis_siteler.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            sonuclar.extend(gelecek.result())

    gorulmus_linkler = set()
    benzersiz_sonuclar = []
    for s in sonuclar:
        anahtar = s.get("Link")
        if anahtar in gorulmus_linkler:
            continue
        gorulmus_linkler.add(anahtar)
        benzersiz_sonuclar.append(s)
    sonuclar = benzersiz_sonuclar

    sonuclar.sort(key=lambda x: fiyat_temizle(x["Fiyat"]))
    return {"sonuclar": sonuclar}
