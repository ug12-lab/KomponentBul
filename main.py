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
    # --- PERAKENDE SİTELER ---
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
    },
    "Direnç.net": {
        "url_sablonu": "https://www.direnc.net/arama?q={}",
        "base_url": "https://www.direnc.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Kartal Otomasyon": {
        "url_sablonu": "https://www.kartalotomasyon.com.tr/arama?q={}",
        "base_url": "https://www.kartalotomasyon.com.tr",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Komponentci": {
        "url_sablonu": "https://www.komponentci.net/Arama.aspx?kelime={}",
        "base_url": "https://www.komponentci.net",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".productItem, .showcase, div[class*='product']"}
    },
    "Samm Market": {
        "url_sablonu": "https://market.samm.com/search?q={}",
        "base_url": "https://market.samm.com",
        "kategori": "Perakende",
        "seciciler": {"kutu": ".product-card, div[class*='product'], a[class*='product']"}
    },
    
    # --- TOPTAN SİTELER ---
    "Merter Elektronik": {
        "url_sablonu": "https://www.merterelektronik.com/Arama.aspx?kelime={}",
        "base_url": "https://www.merterelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".productItem, .showcase, div[class*='product']"}
    },
    "Özdisan": {
        "url_sablonu": "https://ozdisan.com/Search?q={}",
        "base_url": "https://ozdisan.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, div[class*='product']"}
    },
    "Empastore": {
        "url_sablonu": "https://www.empastore.com/arama?q={}",
        "base_url": "https://www.empastore.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".product-item, .showcase, div[class*='product']"}
    },
    "Karaköy Elektronik": {
        "url_sablonu": "https://www.karakoyelektronik.com/arama?q={}",
        "base_url": "https://www.karakoyelektronik.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "F1 Depo": {
        "url_sablonu": "https://www.f1depo.com/arama?q={}",
        "base_url": "https://www.f1depo.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
    },
    "Elektrovadi": {
        "url_sablonu": "https://www.elektrovadi.com/arama?q={}",
        "base_url": "https://www.elektrovadi.com",
        "kategori": "Toptan",
        "seciciler": {"kutu": ".showcase, .product-item, div[data-toggle='product']"}
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

            eklenen_isimler = set()
            sayac = 0

            for urun in urunler:
                if sayac
