import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import pandas as pd
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
import io

# ====================== SABİT LİSTELER ======================
ERDEMIR_SAC_EBATLARI = [
    (1000, 2000), (1250, 2500), (1500, 3000),
    (1500, 6000), (2000, 6000), (2000, 12000)
]

# ====================== VERİ YAPISI ======================
@dataclass
class ParcaSonuc:
    adi: str
    net_kg: float
    fire_kg: float
    brut_kg: float
    fire_yuzde: float
    aciklama: str = ""

# ====================== YARDIMCI FONKSİYONLAR ======================
def polygon_perimeter(N: int, cap_mm: float) -> float:
    k = N * math.tan(math.pi / N)
    return k * cap_mm

def slant_height(net_boy_mm: float, alt_cap_mm: float, ust_cap_mm: float) -> float:
    return math.sqrt(net_boy_mm**2 + ((alt_cap_mm - ust_cap_mm) / 2)**2)

def weight_from_area(area_mm2: float, kalinlik_mm: float) -> float:
    """Alan (mm²) ve kalınlıktan (mm) ağırlık hesapla — çelik yoğunluğu 7.85 g/cm³"""
    return area_mm2 * kalinlik_mm * 7.85 * 1e-6

def safe_fire_pct(fire_kg: float, brut_kg: float) -> float:
    return round(fire_kg / brut_kg * 100, 2) if brut_kg > 0 else 0.0

def get_ankraj_by_boy(net_boy_mm: float) -> dict:
    if net_boy_mm <= 7000:
        return {"tip": "M24x576", "adet": 4, "agirlik_kg": 1.772 * 4}
    elif net_boy_mm <= 9000:
        return {"tip": "M24x784", "adet": 4, "agirlik_kg": 2.4 * 4}
    else:
        return {"tip": "M27x864", "adet": 4, "agirlik_kg": 3.432 * 4}

# ====================== HESAP FONKSİYONLARI ======================
def calculate_govde_sac(
    net_boy_mm: float,
    alt_cap_mm: float,
    ust_cap_mm: float,
    sac_kalinlik_mm: float,
    kenar_sayisi: int,
    kesim_tipi: str,
    ust_sac_boy_mm: Optional[float] = None,
    alt_sac_boy_mm: Optional[float] = None,
    margin_mm: float = 15.0,
) -> List[ParcaSonuc]:
    """
    Govde sac agirlik & fire hesabi.

    Fire mantigi (Excel uyumlu - Asama 3):
      Iki trapez panel head-to-tail ic ice yerlestirilir.
      gross_w = P_alt + P_ust → fire ≈ 0 (sadece mm yuvarlama artigi).
    """
    sonuclar = []
    P_alt = polygon_perimeter(kenar_sayisi, alt_cap_mm)
    P_ust = polygon_perimeter(kenar_sayisi, ust_cap_mm)

    def nested_fire(Pa: float, Pu: float, L: float):
        """Ic-ice kesim: gross_w = ceil(Pa+Pu), fire = yuvarlama artigi per panel."""
        gross_w_pair  = Pa + Pu
        gross_w_ceil  = math.ceil(gross_w_pair)
        net_area      = (Pa + Pu) / 2 * L
        fire_area_per = (gross_w_ceil - gross_w_pair) / 2 * L
        return net_area, fire_area_per, gross_w_ceil

    if kesim_tipi == "Tek Parça Sac":
        L = slant_height(net_boy_mm, alt_cap_mm, ust_cap_mm)
        net_area, fire_area, gross_w = nested_fire(P_alt, P_ust, L)
        net_kg  = weight_from_area(net_area, sac_kalinlik_mm)
        fire_kg = weight_from_area(fire_area, sac_kalinlik_mm)
        brut_kg = net_kg + fire_kg
        sonuclar.append(ParcaSonuc(
            "Gövde (Tek Parça)", round(net_kg, 3), round(fire_kg, 3),
            round(brut_kg, 3), safe_fire_pct(fire_kg, brut_kg),
            f"Ic ice kesim {gross_w:.0f}x{L:.0f} mm (2 panel/plaka)"
        ))

    else:
        L_ust = float(ust_sac_boy_mm or net_boy_mm * 0.55)
        L_alt = float(alt_sac_boy_mm or net_boy_mm * 0.45)
        # Birlesim capi: dogrusal interpolasyon (alt → ust)
        taper   = (alt_cap_mm - ust_cap_mm) / net_boy_mm
        mid_cap = alt_cap_mm - taper * L_alt
        P_mid   = polygon_perimeter(kenar_sayisi, mid_cap)

        # Ust parca: mid_cap → ust_cap
        net_area_ust, fire_area_ust, gross_w_ust = nested_fire(P_mid, P_ust, L_ust)
        net_kg_ust  = weight_from_area(net_area_ust, sac_kalinlik_mm)
        fire_kg_ust = weight_from_area(fire_area_ust, sac_kalinlik_mm)
        brut_kg_ust = net_kg_ust + fire_kg_ust
        sonuclar.append(ParcaSonuc(
            "Gövde Üst Sac", round(net_kg_ust, 3), round(fire_kg_ust, 3),
            round(brut_kg_ust, 3), safe_fire_pct(fire_kg_ust, brut_kg_ust),
            f"Ic ice {gross_w_ust:.0f}x{L_ust:.0f} mm - Birlesim cap {mid_cap:.1f} mm"
        ))

        # Alt parca: alt_cap → mid_cap
        net_area_alt, fire_area_alt, gross_w_alt = nested_fire(P_alt, P_mid, L_alt)
        net_kg_alt  = weight_from_area(net_area_alt, sac_kalinlik_mm)
        fire_kg_alt = weight_from_area(fire_area_alt, sac_kalinlik_mm)
        brut_kg_alt = net_kg_alt + fire_kg_alt
        sonuclar.append(ParcaSonuc(
            "Gövde Alt Sac", round(net_kg_alt, 3), round(fire_kg_alt, 3),
            round(brut_kg_alt, 3), safe_fire_pct(fire_kg_alt, brut_kg_alt),
            f"Ic ice {gross_w_alt:.0f}x{L_alt:.0f} mm - Birlesim cap {mid_cap:.1f} mm"
        ))

    return sonuclar


def calculate_konsol_gecme_boru(
    adet: int,
    boru_uzunluk_mm: float,
    margin_mm: float = 5.0,
    batch_adet: int = 100,
    dis_cap_mm: float = 48.0,
    ic_cap_mm: float = 42.0,
    parca_boy_mm: float = 250.0,
) -> ParcaSonuc:
    if adet == 0:
        return ParcaSonuc("Konsol Geçme Borusu", 0, 0, 0, 0, "Adet = 0")

    # Kesit alanı (mm²) × boy (mm) → hacim (mm³) → kg
    kesit_alan = math.pi * (dis_cap_mm**2 - ic_cap_mm**2) / 4   # mm²
    hacim_per  = kesit_alan * parca_boy_mm                       # mm³ / parça
    net_kg     = hacim_per * 7.85e-6 * adet                      # kg

    kesim_boy  = parca_boy_mm + margin_mm
    fire_orani = kesim_boy / boru_uzunluk_mm
    fire_kg    = net_kg * fire_orani * (adet / batch_adet)

    brut_kg = net_kg + fire_kg
    return ParcaSonuc(
        f"Konsol Geçme Borusu (×{adet})",
        round(net_kg, 3), round(fire_kg, 3), round(brut_kg, 3),
        safe_fire_pct(fire_kg, brut_kg),
        f"Ø{dis_cap_mm:.0f}/{ic_cap_mm:.0f} mm • L={parca_boy_mm:.0f} mm • Boru {boru_uzunluk_mm/1000:.0f} m"
    )


def calculate_taban_plaka(
    flans_boyut_mm: float,
    flans_kalinlik_mm: float,
    ic_cap_mm: float = 0.0,
    margin_mm: float = 15.0,
) -> Tuple[ParcaSonuc, str]:
    """
    Taban plaka net + fire hesabi.

    Net alan = kare dis alan - ic daire (pole gecis deligi).
    Fire     = Erdemir sactan batch kesim artiginin plaka basina pay (Excel mantigi):
               fire_per_plate = sheet_area / num_plates - net_area
    """
    plate_outer_area = flans_boyut_mm ** 2
    ic_alan = math.pi * (ic_cap_mm / 2) ** 2 if ic_cap_mm > 0 else 0.0
    net_area = plate_outer_area - ic_alan
    net_kg   = weight_from_area(net_area, flans_kalinlik_mm)

    best_sac, best_fire = None, float("inf")
    for w, l in ERDEMIR_SAC_EBATLARI:
        plates_w = max(1, int(w / flans_boyut_mm))
        plates_l = max(1, int(l / flans_boyut_mm))
        num = plates_w * plates_l
        # Batch fire: her plaka icin sac artiginin payi
        fire_area_per = w * l / num - net_area
        if fire_area_per < 0:
            fire_area_per = 0.0
        fire_kg = weight_from_area(fire_area_per, flans_kalinlik_mm)
        if fire_kg < best_fire:
            best_fire = fire_kg
            best_sac  = f"{w}x{l} mm ({num} adet/plaka)"

    if best_sac is None:
        best_sac, best_fire = "Yeterli sac bulunamadi", 0.0

    brut_kg = net_kg + best_fire
    return ParcaSonuc(
        "Taban Plaka", round(net_kg, 3), round(best_fire, 3),
        round(brut_kg, 3), safe_fire_pct(best_fire, brut_kg),
        f"Erdemir {best_sac}"
    ), best_sac


def calculate_destek_plaka(
    en_mm: float = 90.0,
    uzunluk_mm: float = 135.0,
    kalinlik_mm: float = 12.0,
    adet: int = 4,
) -> ParcaSonuc:
    """
    Destek plaka (takviye) -- Excel: 12mm x 90 x 135 x 4 adet.
    Fire: Erdemir sac batch kesim mantigi (taban plaka ile ayni yontem).
    """
    net_area_per = en_mm * uzunluk_mm
    net_kg = weight_from_area(net_area_per, kalinlik_mm) * adet

    # Batch fire: sactan kac plaka kesilir (90 ve 135 yon denenir)
    best_sac, best_fire = None, float("inf")
    for w, l in ERDEMIR_SAC_EBATLARI:
        n1 = int(w / en_mm) * int(l / uzunluk_mm)
        n2 = int(w / uzunluk_mm) * int(l / en_mm)   # 90 derece donmus
        num = max(n1, n2)
        if num == 0:
            continue
        fire_per = w * l / num - net_area_per
        if fire_per < 0:
            fire_per = 0.0
        fire_kg = weight_from_area(fire_per, kalinlik_mm) * adet
        if fire_kg < best_fire:
            best_fire = fire_kg
            best_sac  = f"{w}x{l} mm ({num} adet/sac)"

    if best_sac is None:
        best_sac, best_fire = "Sac bulunamadi", 0.0

    brut_kg = net_kg + best_fire
    return ParcaSonuc(
        f"Destek Plaka (x{adet})",
        round(net_kg, 3), round(best_fire, 3), round(brut_kg, 3),
        safe_fire_pct(best_fire, brut_kg),
        f"{kalinlik_mm:.0f}mm x {en_mm:.0f}x{uzunluk_mm:.0f}mm x {adet} adet x {best_sac}"
    )
    kesim_uzunluk = uzunluk_mm + margin_mm
    fire_orani = (kesim_uzunluk % boru_uzunluk_mm) / boru_uzunluk_mm if boru_uzunluk_mm > 0 else 0
    fire_kg = weight_from_area(en_mm * (kesim_uzunluk - uzunluk_mm), kalinlik_mm) * adet

    brut_kg = net_kg + fire_kg
    return ParcaSonuc(
        f"Destek Plaka (×{adet})",
        round(net_kg, 3), round(fire_kg, 3), round(brut_kg, 3),
        safe_fire_pct(fire_kg, brut_kg),
        f"{kalinlik_mm:.0f} mm • {en_mm:.0f}×{uzunluk_mm:.0f} mm • {adet} adet"
    )


def calculate_boru_agirlik(
    dis_cap_mm: float,
    et_mm: float,
    uzunluk_mm: float,
    adet: int,
    aciklama_adi: str,
    standart_boru_mm: float = 6000.0,
) -> ParcaSonuc:
    """Genel boru ağırlık hesabı — tüm konsol boruları için kullanılır."""
    if adet == 0:
        return ParcaSonuc(aciklama_adi, 0, 0, 0, 0, "Adet = 0")

    ic_cap_mm = dis_cap_mm - 2 * et_mm
    kesit_alan = math.pi * (dis_cap_mm**2 - ic_cap_mm**2) / 4  # mm²
    net_kg = kesit_alan * uzunluk_mm * 7.85e-6 * adet

    # Fire: standart borudan artan fire
    adet_per_boru = max(1, int(standart_boru_mm // uzunluk_mm))
    fire_per_boru = standart_boru_mm % uzunluk_mm          # mm
    fire_kg = kesit_alan * fire_per_boru * 7.85e-6 * (adet / adet_per_boru)

    brut_kg = net_kg + fire_kg
    return ParcaSonuc(
        aciklama_adi,
        round(net_kg, 3), round(fire_kg, 3), round(brut_kg, 3),
        safe_fire_pct(fire_kg, brut_kg),
        f"Ø{dis_cap_mm:.0f} (et={et_mm:.0f}mm) • L={uzunluk_mm:.0f}mm × {adet} adet"
    )


def calculate_sigorta_kapagi(
    el_boy_mm: float,
    alt_cap_mm: float,
    kenar_sayisi: int,
    kalinlik_mm: float = 1.5,
    panel_katsayi: float = 2.5,
) -> ParcaSonuc:
    """
    Sigorta kapagi / el-kapi saci.

    Excel referansi: 1.5mm, ~118.585x250mm, 0.349 kg
    Genislik = 2.5 x alt panel genisligi (2 yuzey + montaj flansi)
    Fire     = batch kesim (1000x2000 sactan 64 adet)
    """
    panel_genislik = polygon_perimeter(kenar_sayisi, alt_cap_mm) / kenar_sayisi
    genislik = panel_katsayi * panel_genislik
    net_area = genislik * el_boy_mm
    net_kg   = weight_from_area(net_area, kalinlik_mm)

    # Batch fire: sactan kac kapak kesilir
    best_sac, best_fire = None, float("inf")
    for w, l in ERDEMIR_SAC_EBATLARI:
        num_w = max(1, int(w / genislik))
        num_l = max(1, int(l / el_boy_mm))
        num   = num_w * num_l
        fire_area_per = w * l / num - net_area
        if fire_area_per < 0:
            fire_area_per = 0.0
        fire_kg = weight_from_area(fire_area_per, kalinlik_mm)
        if fire_kg < best_fire:
            best_fire = fire_kg
            best_sac  = f"{w}x{l} mm ({num} adet/sac)"

    if best_sac is None:
        best_sac, best_fire = "Manuel sec", 0.0

    brut_kg = net_kg + best_fire
    return ParcaSonuc(
        "Sigorta Kapagi (El/Kapi)",
        round(net_kg, 3), round(best_fire, 3), round(brut_kg, 3),
        safe_fire_pct(best_fire, brut_kg),
        f"{kalinlik_mm}mm x {genislik:.1f}x{el_boy_mm:.0f}mm x Erdemir {best_sac}"
    )

    # Fire: en yakın Erdemir sacından
    best_sac, min_fire = None, float("inf")
    for w, l in ERDEMIR_SAC_EBATLARI:
        if w >= panel_genislik + 2 * margin_mm and l >= el_boy_mm + 2 * margin_mm:
            fire = weight_from_area(w * l - net_area, kalinlik_mm)
            if fire < min_fire:
                min_fire = fire
                best_sac = f"{w}×{l} mm"
    if best_sac is None:
        best_sac, min_fire = "Manuel seç", 0.0

    brut_kg = net_kg + min_fire
    return ParcaSonuc(
        "Sigorta Kapağı (El/Kapı)",
        round(net_kg, 3), round(min_fire, 3), round(brut_kg, 3),
        safe_fire_pct(min_fire, brut_kg),
        f"{kalinlik_mm}mm • {panel_genislik:.1f}×{el_boy_mm:.0f}mm • Erdemir {best_sac}"
    )


def calculate_topraklama_levhasi(dahil: bool = True) -> ParcaSonuc:
    """Topraklama levhası — Excel: 3mm • 30×80mm • 1 adet • 0.057 kg."""
    if not dahil:
        return ParcaSonuc("Topraklama Levhası", 0, 0, 0, 0, "Dahil değil")
    net_kg = weight_from_area(30.0 * 80.0, 3.0)
    return ParcaSonuc(
        "Topraklama Levhası",
        round(net_kg, 3), 0.0, round(net_kg, 3), 0.0,
        "3mm • 30×80mm • 1 adet"
    )


def calculate_sigorta_rayi(dahil: bool = True) -> ParcaSonuc:
    """Sigorta rayi (omega/U profil) -- Excel: 1mm * 45x226.775mm * 1 adet * 0.091 kg."""
    if not dahil:
        return ParcaSonuc("Sigorta Rayi", 0, 0, 0, 0, "Dahil degil")
    net_kg = weight_from_area(45.0 * 226.775, 1.0)
    return ParcaSonuc(
        "Sigorta Rayi",
        round(net_kg, 3), 0.0, round(net_kg, 3), 0.0,
        "1mm * 45x226.775mm * 1 adet"
    )

def calculate_sablon(boyut_mm: float = 440.0, dahil: bool = True) -> ParcaSonuc:
    """Şablon — Excel: 1.5mm • 440×440mm • 0.1 adet (10 direkte 1 şablon) • 0.228 kg."""
    if not dahil:
        return ParcaSonuc("Şablon", 0, 0, 0, 0, "Dahil değil")
    net_kg = weight_from_area(boyut_mm ** 2, 1.5) * 0.1  # 0.1 adet
    return ParcaSonuc(
        "Şablon (batch 1/10)",
        round(net_kg, 3), 0.0, round(net_kg, 3), 0.0,
        f"1.5mm • {boyut_mm:.0f}×{boyut_mm:.0f}mm • 0.1 adet"
    )


# ====================== ANA HESAP ======================
def run_all(params: dict) -> Tuple[List[ParcaSonuc], pd.DataFrame, dict]:
    """Tüm bileşenleri hesapla, DataFrame ve özet döndür."""
    govde = calculate_govde_sac(
        params["net_boy"], params["alt_cap"], params["ust_cap"],
        params["kalinlik"], params["kenar"], params["kesim_tipi"],
        params.get("ust_sac_boy"), params.get("alt_sac_boy"),
        float(params["margin"]),
    )

    # ── Taban Plaka + Destek Plaka (ayrı ayrı) ──────────────────────────────
    taban, _ = calculate_taban_plaka(
        float(params["flans_boyut"]), float(params["flans_kalinlik"]),
        ic_cap_mm=float(params["flans_ic_cap"]),
        margin_mm=float(params["margin"])
    )
    destek = calculate_destek_plaka(
        en_mm=float(params["destek_en"]),
        uzunluk_mm=float(params["destek_uzunluk"]),
        kalinlik_mm=float(params["destek_kalinlik"]),
        adet=int(params["destek_adet"]),
    )

    # ── Konsol Boruları (her tip ayrı) ──────────────────────────────────────
    k = params["konsol"]
    konsol_borular = []
    if k["govde_adet"] > 0:
        konsol_borular.append(calculate_boru_agirlik(
            k["govde_dis_cap"], k["govde_et"], k["govde_uzunluk"],
            k["govde_adet"], "Konsol Gövde Borusu", params["boru_uzunluk"]
        ))
    if k["dirsek_adet"] > 0:
        konsol_borular.append(calculate_boru_agirlik(
            k["dirsek_dis_cap"], k["dirsek_et"], k["dirsek_uzunluk"],
            k["dirsek_adet"], "Konsol Dirsek Borusu", params["boru_uzunluk"]
        ))
    if k["uc_adet"] > 0:
        konsol_borular.append(calculate_boru_agirlik(
            k["uc_dis_cap"], k["uc_et"], k["uc_uzunluk"],
            k["uc_adet"], "Konsol Uç Borusu", params["boru_uzunluk"]
        ))
    if k["gecme_adet"] > 0:
        konsol_borular.append(calculate_boru_agirlik(
            48.0, 3.0, 250.0,
            k["gecme_adet"], "Konsol Geçme Borusu", params["boru_uzunluk"]
        ))

    ankraj      = get_ankraj_by_boy(params["net_boy"])
    ankraj_net  = round(ankraj["agirlik_kg"], 3)
    ankraj_sonuc = ParcaSonuc(
        "Ankraj + Somun + Rondela", ankraj_net, 0, ankraj_net, 0,
        f"{ankraj['tip']} × {ankraj['adet']} adet"
    )

    # ── Aşama 2: Ek Parçalar ────────────────────────────────────────────
    sigorta = calculate_sigorta_kapagi(
        el_boy_mm=float(params["el_boy"]),
        alt_cap_mm=params["alt_cap"],
        kenar_sayisi=params["kenar"],
    )
    topraklama = calculate_topraklama_levhasi(dahil=params["topraklama_dahil"])
    sigorta_rayi = calculate_sigorta_rayi(dahil=params["sigorta_rayi_dahil"])
    sablon     = calculate_sablon(boyut_mm=float(params["sablon_boyut"]),
                                  dahil=params["sablon_dahil"])

    tum = govde + [taban, destek] + konsol_borular + [sigorta, topraklama, sigorta_rayi, sablon, ankraj_sonuc]

    # DataFrame
    df = pd.DataFrame([{
        "Parça"       : p.adi,
        "Net kg"      : p.net_kg,
        "Fire kg"     : p.fire_kg,
        "Brüt kg"     : p.brut_kg,
        "Fire %"      : p.fire_yuzde,
        "Açıklama"    : p.aciklama,
    } for p in tum])

    toplam_net  = df["Net kg"].sum()
    toplam_fire = df["Fire kg"].sum()
    toplam_brut = df["Brüt kg"].sum()

    galvaniz_ek    = toplam_net * params["galvaniz"] / 100
    galvanizli_net = toplam_net + galvaniz_ek

    ozet = {
        "toplam_net"    : round(toplam_net, 2),
        "toplam_fire"   : round(toplam_fire, 2),
        "toplam_brut"   : round(toplam_brut, 2),
        "galvaniz_ek"   : round(galvaniz_ek, 2),
        "galvanizli_net": round(galvanizli_net, 2),
        "fire_pct"      : round(toplam_fire / toplam_brut * 100, 2) if toplam_brut > 0 else 0,
        "ankraj_tip"    : ankraj["tip"],
    }
    return tum, df, ozet



# ====================== HTML RAPOR ======================
def generate_html_report(params: dict, df, ozet: dict) -> str:
    """Indirilebilir HTML rapor olusturur (tarayicidan PDF yapilabilir)."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    rows = ""
    for _, r in df.iterrows():
        fire_style = "color:#e63946;font-weight:600;" if r["Fire %"] > 5 else ""
        rows += (
            f"<tr><td>{r['Parça']}</td>"
            f"<td style='text-align:right'>{r['Net kg']:.3f}</td>"
            f"<td style='text-align:right;{fire_style}'>{r['Fire kg']:.3f}</td>"
            f"<td style='text-align:right'>{r['Brüt kg']:.3f}</td>"
            f"<td style='text-align:right;{fire_style}'>{r['Fire %']:.1f}%</td>"
            f"<td style='font-size:11px;color:#555'>{r['Açıklama']}</td></tr>"
        )
    kesim = params.get("kesim_tipi", "-")
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Poligon Direk Agirlik Raporu</title>
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;margin:30px;color:#1a1a2e;font-size:13px}}
  h1{{color:#0f3460;border-bottom:3px solid #0f3460;padding-bottom:8px;font-size:22px}}
  h2{{color:#16213e;font-size:15px;margin-top:24px;margin-bottom:6px;
      border-left:4px solid #0f3460;padding-left:8px}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}}
  .card{{background:#f0f4ff;border-radius:8px;padding:12px 16px;text-align:center}}
  .card-val{{font-size:20px;font-weight:700;color:#0f3460}}
  .card-lbl{{font-size:11px;color:#555;margin-top:2px}}
  .card-hi{{background:#fff3cd}}
  table{{border-collapse:collapse;width:100%;margin-top:8px}}
  th{{background:#0f3460;color:#fff;padding:7px 10px;text-align:left;font-size:12px}}
  td{{padding:5px 10px;border-bottom:1px solid #dde3f0;font-size:12px}}
  tr:nth-child(even){{background:#f7f9ff}}
  .params{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;font-size:12px}}
  .param-item{{background:#f0f4ff;border-radius:5px;padding:6px 10px}}
  .param-key{{color:#888;font-size:10px}}
  .param-val{{font-weight:600;color:#0f3460}}
  footer{{margin-top:30px;font-size:10px;color:#aaa;text-align:center}}
  @media print{{body{{margin:15px}}.no-print{{display:none}}}}
</style>
</head>
<body>
<h1>&#x1F3D7;&#xFE0F; Poligon Aydinlatma Diregi &mdash; Agirlik &amp; Fire Raporu</h1>
<p style="color:#666;font-size:12px">Olusturulma: {now} &nbsp;|&nbsp; TEDAS APD-96/1-A uyumlu &nbsp;|&nbsp; Erdemir sac</p>

<h2>Ozet</h2>
<div class="grid">
  <div class="card">
    <div class="card-val">{ozet['toplam_net']} kg</div>
    <div class="card-lbl">Net Agirlik</div>
  </div>
  <div class="card card-hi">
    <div class="card-val">{ozet['toplam_fire']} kg</div>
    <div class="card-lbl">Toplam Fire ({ozet['fire_pct']}%)</div>
  </div>
  <div class="card">
    <div class="card-val">{ozet['toplam_brut']} kg</div>
    <div class="card-lbl">Brut (Hammadde)</div>
  </div>
  <div class="card">
    <div class="card-val">{ozet['galvaniz_ek']} kg</div>
    <div class="card-lbl">Galvaniz Ek (+%{params.get('galvaniz',5.5)})</div>
  </div>
  <div class="card" style="background:#e8f5e9">
    <div class="card-val" style="color:#2e7d32">{ozet['galvanizli_net']} kg</div>
    <div class="card-lbl">Galvanizli Toplam</div>
  </div>
</div>

<h2>Giris Parametreleri</h2>
<div class="params">
  <div class="param-item"><div class="param-key">Net Boy</div>
    <div class="param-val">{params.get('net_boy','-')} mm</div></div>
  <div class="param-item"><div class="param-key">Alt Cap</div>
    <div class="param-val">O{params.get('alt_cap','-')} mm</div></div>
  <div class="param-item"><div class="param-key">Ust Cap</div>
    <div class="param-val">O{params.get('ust_cap','-')} mm</div></div>
  <div class="param-item"><div class="param-key">Sac Kalinligi</div>
    <div class="param-val">{params.get('kalinlik','-')} mm</div></div>
  <div class="param-item"><div class="param-key">Kenar Sayisi</div>
    <div class="param-val">{params.get('kenar','-')}</div></div>
  <div class="param-item"><div class="param-key">Kesim Tipi</div>
    <div class="param-val">{kesim}</div></div>
  <div class="param-item"><div class="param-key">Flans Boyutu</div>
    <div class="param-val">{params.get('flans_boyut','-')} mm</div></div>
  <div class="param-item"><div class="param-key">Flans Kalinligi</div>
    <div class="param-val">{params.get('flans_kalinlik','-')} mm</div></div>
</div>

<h2>Malzeme Listesi</h2>
<table>
  <thead>
    <tr>
      <th>Parca</th><th>Net kg</th><th>Fire kg</th>
      <th>Brut kg</th><th>Fire %</th><th>Aciklama</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<footer>
  Bu rapor Poligon Direk Agirlik Hesaplayici tarafindan otomatik olusturulmustur.
  Tarayicinizdan Dosya &rarr; Yazdir &rarr; PDF olarak kaydet ile PDF alabilirsiniz.
</footer>
</body>
</html>"""
    return html

# ====================== STREAMLIT UYGULAMASI ======================
st.set_page_config(
    page_title="Poligon Direk Hesaplayıcı",
    layout="wide",
    page_icon="🏗️",
)

st.title("🏗️ Poligon Aydınlatma Direği — Canlı Ağırlık & Fire Hesaplayıcı")
st.caption("**TEDAŞ APD-96/1-A** uyumlu • Erdemir sac • Parametreler değiştikçe sonuçlar anında güncellenir")

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Direk Parametreleri")

    st.subheader("Boyutlar")
    net_boy    = st.number_input("Net Boy (mm)",         value=8000,  min_value=1000,  step=100)
    alt_cap    = st.number_input("Alt Çap (mm)",         value=175.6, min_value=100.0, step=10.0, format="%.1f")
    ust_cap    = st.number_input("Üst Çap (mm)",         value=60.0,  min_value=30.0,  step=5.0,  format="%.1f")
    kalinlik   = st.number_input("Sac Kalınlığı (mm)",   value=3.0,   min_value=2.0,   step=0.5,  format="%.1f")
    kenar      = st.selectbox("Kenar Sayısı",            [8, 12],     index=1)

    st.subheader("Gövde Kesim Tipi")
    kesim_tipi = st.radio("", ["Tek Parça Sac", "İki Parça Sac (Üst + Alt)"], horizontal=True)

    ust_sac_boy = alt_sac_boy = None
    if kesim_tipi == "İki Parça Sac (Üst + Alt)":
        ust_sac_boy = st.number_input("Üst Sac Boyu (mm)", value=int(net_boy * 0.55), step=50)
        alt_sac_boy = st.number_input("Alt Sac Boyu (mm)", value=int(net_boy * 0.45), step=50)

    st.subheader("Flanş")
    flans_boyut   = st.number_input("Flanş Boyutu (mm)",  value=400, step=10)
    flans_kalinlik = st.number_input("Flanş Kalınlığı (mm)", value=18, step=1)
    flans_ic_cap = st.number_input(
        "Flanş İç Çap (delme çapı, mm)",
        value=240, min_value=0, step=5,
        help="Pole geçiş deliği çapı. 0 girilirse delik yok sayılır.")
    topraklama_dahil = st.checkbox("Topraklama Levhası Dahil", value=True)
    sigorta_rayi_dahil = st.checkbox("Sigorta Rayı Dahil", value=True)

    st.subheader("Flanş Destek Plaka")
    destek_adet     = st.number_input("Destek Plaka Adedi",    value=4,   min_value=0, max_value=8)
    destek_kalinlik = st.number_input("Destek Plaka Kalınlık (mm)", value=12, min_value=4, step=2)
    destek_en       = st.number_input("Destek Plaka En (mm)",   value=90,  min_value=20, step=5)
    destek_uzunluk  = st.number_input("Destek Plaka Boy (mm)",  value=135, min_value=50, step=5)

    st.subheader("Konsol Boruları")
    boru_uzunluk = st.selectbox("Standart Boru Uzunluğu (mm)", [6000, 12000])
    with st.expander("Gövde Borusu"):
        k_govde_adet     = st.number_input("Adet",        value=2, min_value=0, max_value=6, key="kg_adet")
        k_govde_dis_cap  = st.number_input("Dış Çap (mm)",value=60.0, min_value=20.0, step=5.0, key="kg_cap", format="%.1f")
        k_govde_et       = st.number_input("Et Kalınlığı (mm)", value=3.0, min_value=1.5, step=0.5, key="kg_et", format="%.1f")
        k_govde_uzunluk  = st.number_input("Uzunluk (mm)",value=1030, min_value=100, step=10, key="kg_uzun")
    with st.expander("Dirsek Borusu"):
        k_dirsek_adet    = st.number_input("Adet",        value=1, min_value=0, max_value=4, key="kd_adet")
        k_dirsek_dis_cap = st.number_input("Dış Çap (mm)",value=60.0, min_value=20.0, step=5.0, key="kd_cap", format="%.1f")
        k_dirsek_et      = st.number_input("Et Kalınlığı (mm)", value=3.0, min_value=1.5, step=0.5, key="kd_et", format="%.1f")
        k_dirsek_uzunluk = st.number_input("Uzunluk (mm)",value=708,  min_value=100, step=10, key="kd_uzun")
    with st.expander("Uç Borusu"):
        k_uc_adet        = st.number_input("Adet",        value=2, min_value=0, max_value=4, key="ku_adet")
        k_uc_dis_cap     = st.number_input("Dış Çap (mm)",value=48.0, min_value=20.0, step=5.0, key="ku_cap", format="%.1f")
        k_uc_et          = st.number_input("Et Kalınlığı (mm)", value=3.0, min_value=1.5, step=0.5, key="ku_et", format="%.1f")
        k_uc_uzunluk     = st.number_input("Uzunluk (mm)",value=170,  min_value=50,  step=10, key="ku_uzun")
    with st.expander("Geçme Borusu"):
        k_gecme_adet     = st.number_input("Adet",        value=1, min_value=0, max_value=4, key="kgecme_adet")

    st.subheader("Diğer")
    el_boy   = st.number_input("El / Kapı Boyu (mm)", value=250, min_value=100, step=25,
                               help="Sigorta kapağı uzunluğu; genişlik üst çaptan otomatik hesaplanır")
    sablon_dahil = st.checkbox("Şablon Dahil (0.1 adet)", value=True)
    sablon_boyut = st.number_input("Şablon Boyutu (mm)", value=440, min_value=200, step=10,
                                   disabled=not sablon_dahil)
    margin   = st.number_input("Kesim Margin (mm)", value=15, step=5)
    galvaniz = st.number_input("Galvaniz Ek %",     value=5.5, step=0.5, format="%.1f")

# ─── CANLI HESAP ─────────────────────────────────────────────────────────────
params = dict(
    net_boy=net_boy, alt_cap=alt_cap, ust_cap=ust_cap,
    kalinlik=kalinlik, kenar=kenar, kesim_tipi=kesim_tipi,
    ust_sac_boy=ust_sac_boy, alt_sac_boy=alt_sac_boy,
    flans_boyut=flans_boyut, flans_kalinlik=flans_kalinlik, flans_ic_cap=flans_ic_cap,
    topraklama_dahil=topraklama_dahil,
    sigorta_rayi_dahil=sigorta_rayi_dahil,
    destek_adet=destek_adet, destek_kalinlik=destek_kalinlik,
    destek_en=destek_en, destek_uzunluk=destek_uzunluk,
    el_boy=el_boy, sablon_dahil=sablon_dahil, sablon_boyut=sablon_boyut,
    boru_uzunluk=boru_uzunluk, margin=margin, galvaniz=galvaniz,
    konsol=dict(
        govde_adet=k_govde_adet,    govde_dis_cap=k_govde_dis_cap,
        govde_et=k_govde_et,        govde_uzunluk=k_govde_uzunluk,
        dirsek_adet=k_dirsek_adet,  dirsek_dis_cap=k_dirsek_dis_cap,
        dirsek_et=k_dirsek_et,      dirsek_uzunluk=k_dirsek_uzunluk,
        uc_adet=k_uc_adet,          uc_dis_cap=k_uc_dis_cap,
        uc_et=k_uc_et,              uc_uzunluk=k_uc_uzunluk,
        gecme_adet=k_gecme_adet,
    ),
)

tum_sonuclar, df, ozet = run_all(params)

# ─── ÜST METRİK KARTI SATIRI ─────────────────────────────────────────────────
st.subheader("📊 Özet")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🔩 Net Ağırlık",       f"{ozet['toplam_net']} kg")
c2.metric("♻️ Toplam Fire",       f"{ozet['toplam_fire']} kg",   f"% {ozet['fire_pct']}")
c4.metric("🔧 Galvaniz (+%)",     f"{ozet['galvaniz_ek']} kg",   f"+ %{galvaniz}")
c5.metric("✅ Galvanizli Toplam", f"{ozet['galvanizli_net']} kg")
c3.metric("📦 Brüt (hammadde)",   f"{ozet['toplam_brut']} kg")


# --- GRAFIK BOLUMU -------------------------------------------
with st.expander("📊 Agirlik Dagilimi Grafikleri", expanded=False):
    tab1, tab2 = st.tabs(["Net Agirlik", "Net vs Fire"])

    df_plot = df[df["Net kg"] > 0].copy()

    with tab1:
        fig1 = px.bar(
            df_plot.sort_values("Net kg"),
            x="Net kg", y="Parça", orientation="h",
            color="Net kg",
            color_continuous_scale="Blues",
            labels={"Net kg": "Net Agirlik (kg)", "Parça": ""},
            text="Net kg",
        )
        fig1.update_traces(texttemplate="%{text:.2f} kg", textposition="outside")
        fig1.update_layout(
            height=max(350, len(df_plot) * 38),
            margin=dict(l=0, r=40, t=20, b=20),
            coloraxis_showscale=False,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig1, use_container_width=True)

    with tab2:
        df_stacked = df_plot[df_plot["Brüt kg"] > 0].copy()
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            name="Net kg", x=df_stacked["Parça"], y=df_stacked["Net kg"],
            marker_color="#0f3460",
        ))
        fig2.add_trace(go.Bar(
            name="Fire kg", x=df_stacked["Parça"], y=df_stacked["Fire kg"],
            marker_color="#e63946",
        ))
        fig2.update_layout(
            barmode="stack",
            height=400,
            margin=dict(l=0, r=0, t=20, b=80),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig2.update_xaxes(tickangle=-40)
        st.plotly_chart(fig2, use_container_width=True)

# --- HTML RAPOR INDIRME --------------------------------------
html_report = generate_html_report(params, df, ozet)
col_dl1, col_dl2 = st.columns([1, 5])
with col_dl1:
    st.download_button(
        label="⬇️ Raporu İndir (HTML)",
        data=html_report.encode("utf-8"),
        file_name=f"direk_rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
        mime="text/html",
        use_container_width=True,
    )
with col_dl2:
    st.caption("HTML dosyasini tarayicida acip **Dosya → Yazdir → PDF** ile PDF alabilirsiniz.")

st.divider()

# ─── UYARI / BİLGİ PANELİ ────────────────────────────────────────────────────
uyarilar = []
if ust_cap >= alt_cap:
    uyarilar.append("⚠️ **Üst çap ≥ Alt çap** — konik olmayan / ters konik direk!")
if ozet["fire_pct"] > 30:
    uyarilar.append(f"⚠️ **Fire oranı yüksek** (%{ozet['fire_pct']:.1f}) — sac boyutlarını gözden geçirin.")
if kesim_tipi == "İki Parça Sac (Üst + Alt)" and ust_sac_boy and alt_sac_boy:
    toplam_sac = ust_sac_boy + alt_sac_boy
    if abs(toplam_sac - net_boy) > 200:
        uyarilar.append(f"⚠️ **Sac boyları toplamı** ({toplam_sac} mm) net boydan ({net_boy} mm) farklı!")
if flans_boyut < alt_cap:
    uyarilar.append("ℹ️ Taban flanş boyutu alt çaptan küçük — kontrol edin.")

if uyarilar:
    with st.expander("🔔 Uyarılar / Kontrol Noktaları", expanded=True):
        for u in uyarilar:
            st.markdown(u)

# ─── DETAY TABLOSU ───────────────────────────────────────────────────────────
st.subheader("📋 Parça Detayları")
styled = df.style.format({
    "Net kg" : "{:.3f}",
    "Fire kg": "{:.3f}",
    "Brüt kg": "{:.3f}",
    "Fire %" : "{:.2f}",
}).bar(subset=["Fire %"], color="#ff6b6b", vmin=0, vmax=50)

st.dataframe(styled, use_container_width=True, height=320)

# ─── EKSTRA BİLGİ SATIRI ─────────────────────────────────────────────────────
with st.expander("ℹ️ Hesap Detayları"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Ankraj tipi:** `{ozet['ankraj_tip']} × 4 adet`")
        st.markdown(f"**Gövde eğim yüksekliği:** `{slant_height(net_boy, alt_cap, ust_cap):.1f} mm`")
        st.markdown(f"**Alt çevre (Polygon):** `{polygon_perimeter(kenar, alt_cap):.1f} mm`")
        st.markdown(f"**Üst çevre (Polygon):** `{polygon_perimeter(kenar, ust_cap):.1f} mm`")
    with col_b:
        st.markdown(f"**Konsol Gövde Borusu:** `{k_govde_adet} × Ø{k_govde_dis_cap:.0f}mm / {k_govde_uzunluk} mm`")
        st.markdown(f"**Konsol Dirsek Borusu:** `{k_dirsek_adet} × Ø{k_dirsek_dis_cap:.0f}mm / {k_dirsek_uzunluk} mm`")
        st.markdown(f"**Konsol Uç+Geçme Borusu:** `{k_uc_adet}+{k_gecme_adet} adet`")
        st.markdown(f"**Galvaniz katsayısı:** `%{galvaniz}`")
        st.markdown(f"**Kesim margin:** `{margin} mm`")

# ─── İNDİRME ─────────────────────────────────────────────────────────────────
st.subheader("📥 Dışa Aktar")
col_dl1, col_dl2 = st.columns(2)

csv = df.to_csv(index=False).encode("utf-8")
col_dl1.download_button(
    "⬇️ CSV İndir", csv,
    file_name=f"direk_{net_boy}mm.csv",
    mime="text/csv",
    use_container_width=True,
)

excel_buf = io.BytesIO()
with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Ağırlık ve Fire")
    # Özet sayfası
    ozet_df = pd.DataFrame([{
        "Toplam Net kg"      : ozet["toplam_net"],
        "Toplam Fire kg"     : ozet["toplam_fire"],
        "Toplam Brüt kg"     : ozet["toplam_brut"],
        "Galvaniz Ek kg"     : ozet["galvaniz_ek"],
        "Galvanizli Net kg"  : ozet["galvanizli_net"],
        "Fire %"             : ozet["fire_pct"],
    }])
    ozet_df.to_excel(writer, index=False, sheet_name="Özet")

col_dl2.download_button(
    "⬇️ Excel İndir", excel_buf.getvalue(),
    file_name=f"direk_{net_boy}mm.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption("🔧 Canlı mod — sidebar'daki her değişiklik sonuçları anında günceller")