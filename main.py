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
    allow_credentials=False,  # "*" ile allow_credentials=True birlikte kullanılamaz
    allow_methods=["*"],
    allow_headers=["*"],
)

TEDARIKCILER = {
    "Elektromarketim": {
        "url_sablonu": "https://www.elektromarketim.com/arama?q={}",
        "base_url": "https://www.elektromarketim.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".ems-prd, .product-item, div[class*='product']"}
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
        "seciciler": {"kutu": ".showcase, div[class*='product'], li[class*='product']"}
    },
    "Robolink": {
        "url_sablonu": "https://www.robolinkmarket.com/arama?q={}",
        "base_url": "https://www.robolinkmarket.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-item, .product-box"}
    }
}

# CSS ile gizlenmiş (görünmez) elementleri tespit etmek için kullanılan class/attribute'lar.
# Birçok site (ör. Robolink) "Tükendi" bloğunu HER üründe DOM'a basar, sadece
# stoktaysa bu bloğu bu class'larla gizler. Bu yüzden salt metin araması yanıltıcıdır.
GIZLI_ISARETLERI = {"d-none", "hidden", "invisible", "display-none", "hide"}


def gorunur_mu(etiket):
    """Bir elementin (veya üst elementlerinden birinin) CSS ile gizlenip
    gizlenmediğini kontrol eder. Gizliyse False döner."""
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
    """'2.151,00 TL' -> 2151.00"""
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

            eklenen_isimler = set()
            sayac = 0

            for urun in urunler:
                if sayac >= 5:
                    break

                try:
                    isim = ""
                    link = url

                    # 1. İSİM BULUCU
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
                    # "Tükendi" bloğu CSS ile gizlenmişse (d-none vb.) bu ürün aslında stokta demektir.
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

                    # 3. FİYAT BULUCU (birden fazla eşleşme varsa en düşüğünü/güncel fiyatı seç —
                    # indirimli ürünlerde üstü çizili eski fiyat metinde önce geçtiği için yanlış
                    # fiyat seçilmesini engeller)
                    raw_text = urun.text.replace('\n', ' ')
                    raw_text = re.sub(r'\{.*?\}', '', raw_text)

                    if not stokta_yok_mu:
                        fiyat_eslesmeler = re.findall(
                            r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:TL|₺|tl)',
                            raw_text, re.IGNORECASE
                        )
                        gecerli = []
                        for e in fiyat_eslesmeler:
                            sayi = metni_sayiya_cevir(e)
                            if sayi and sayi > 0:
                                gecerli.append((sayi, e))

                        if gecerli:
                            gecerli.sort(key=lambda x: x[0])
                            _, en_uygun_metin = gecerli[0]
                            fiyat = en_uygun_metin.upper().replace('₺', ' TL').strip()
                            if "TL" not in fiyat:
                                fiyat += " TL"
                            fiyat_gosterim = fiyat
                            stok_durum = "Canlı Veri"
                        else:
                            alternatif_sayi = re.search(r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})', raw_text)
                            if alternatif_sayi:
                                fiyat_gosterim = alternatif_sayi.group(0) + " TL"
                                stok_durum = "Canlı Veri"

                    # 4. ÇÖP FİLTRESİ
                    if not stokta_yok_mu and stok_durum == "Tükendi":
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
def arama_yap(q: str):
    sonuclar = []
    q_encoded = urllib.parse.quote(q)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        gelecek_sonuclar = [executor.submit(site_tara, ad, ayarlar, q_encoded) for ad, ayarlar in TEDARIKCILER.items()]
        for gelecek in concurrent.futures.as_completed(gelecek_sonuclar):
            sonuclar.extend(gelecek.result())

    # TEKİLLEŞTİRME: Genel (wildcard) CSS seçiciler ("div[class*='product']" gibi)
    # bazen aynı ürünün hem dış hem iç sarmalayıcı div'ini ayrı ayrı eşleştirip
    # aynı ürünü listeye iki kez ekleyebiliyor. Ürün linki her zaman benzersiz
    # olduğu için (aynı ürün = aynı link) buna göre tekilleştiriyoruz.
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
