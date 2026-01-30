import streamlit as st
import ee
import geemap
import os
import geopandas as gpd
import json
import shutil
from zipfile import ZipFile
import glob
from shapely.geometry import shape, mapping
from shapely.ops import transform
import shapely.wkb
import base64

# =========================================================
# 1. KONFIGURASI TAMPILAN (CSS FIX COLOR)
# =========================================================
st.set_page_config(page_title="Analisis PAPAPS", layout="wide", page_icon="🌲")

def set_background(image_file):
    with open(image_file, "rb") as f:
        data = f.read()
    bin_str = base64.b64encode(data).decode()
    
    # CSS Custom: Background Gambar + Konten Putih + Teks Hitam (Wajib)
    page_bg_img = f"""
    <style>
    /* 1. Background Gambar Hutan */
    [data-testid="stAppViewContainer"] {{
        background-image: url("data:image/jpg;base64,{bin_str}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    
    /* 2. Header Transparan */
    [data-testid="stHeader"] {{
        background-color: rgba(0,0,0,0);
    }}

    /* 3. Kotak Konten (Glassmorphism) */
    .block-container {{
        background-color: rgba(255, 255, 255, 0.95); /* Putih Pekat 95% */
        border-radius: 15px;
        padding: 3rem !important;
        margin-top: 2rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        max-width: 1200px;
    }}
    
    /* 4. FIX WARNA TEKS (PENTING BIAR KELIHATAN) */
    /* Paksa semua judul jadi Hijau Tua */
    h1, h2, h3, h4, h5, h6 {{
        color: #1b5e20 !important; 
        font-weight: 700 !important;
    }}
    
    /* Paksa semua teks biasa jadi Hitam/Abu Tua */
    p, div, label, span, li {{
        color: #212121 !important;
    }}
    
    /* Garis Pembatas */
    hr {{
        border-top: 3px solid #1b5e20 !important;
        margin-top: 0px;
        margin-bottom: 30px;
    }}
    
    /* Perbaikan warna teks di dalam Widget (Dropdown/Upload) */
    .stSelectbox label, .stFileUploader label {{
        color: #1b5e20 !important;
        font-weight: bold !important;
        font-size: 1.1em !important;
    }}
    </style>
    """
    st.markdown(page_bg_img, unsafe_allow_html=True)

# Pasang Background
if os.path.exists("hutan.jpg"):
    set_background("hutan.jpg")

# Judul Utama (Updated)
st.markdown("<h1 style='text-align: center;'>🌲 Analisis Peta Arahan Perhutanan Sosial</h1>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# 2. AUTH GEE
# =========================================================
try:
    if "gcp_service_account" in st.secrets:
        service_account = st.secrets["gcp_service_account"]
        credentials = ee.ServiceAccountCredentials(
            service_account["client_email"],
            key_data=service_account["private_key"]
        )
        ee.Initialize(credentials=credentials, project='papaps')
    else:
        ee.Initialize(project='papaps')
except Exception as e:
    st.error(f"Gagal Koneksi GEE: {e}")
    st.stop()

# =========================================================
# 3. MAPPING PROVINSI (LENGKAP)
# =========================================================
ASSET_MAPPING = {
    "Jawa Tengah & DIY": "JatengJogja",
    "Jawa Barat & Jakarta": "Jabar",
    "Jawa Timur": "Jatim",
    "Bali": "Bali",
    "Nusa Tenggara (NTB/NTT)": "Nusra",
    "Sumatera (Aceh, Sumut, Sumbar)": "Sumatera1",
    "Sumatera (Riau, Jambi, Sumsel, Lampung, Babel, Bengkulu)": "Sumatera2",
    "Kalimantan": "Kalimantan",
    "Sulawesi & Gorontalo": "Sulawesi",
    "Maluku": "Maluku",
    "Papua": "Papua"
}

# =========================================================
# 4. FUNGSI LOGIKA (TETAP SAMA)
# =========================================================
def get_sanitized_geometry(zip_file):
    temp_dir = "temp_input"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    with ZipFile(zip_file, 'r') as z: z.extractall(temp_dir)
    shp_path = glob.glob(os.path.join(temp_dir, "**/*.shp"), recursive=True)[0]
    gdf = gpd.read_file(shp_path).to_crs("EPSG:4326")
    ee_features = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom.has_z:
            geom = shapely.wkb.loads(shapely.wkb.dumps(geom, output_dimension=2))
        geom = geom.buffer(0).simplify(0.00001, preserve_topology=True)
        geom_json = mapping(geom)
        ee_features.append(ee.Feature(ee.Geometry(geom_json), {'dummy': 1}))
    return ee.FeatureCollection(ee_features).geometry()

def calculate_attributes(feature):
    def to_num(cond): return ee.Number(ee.Algorithms.If(cond, 1, 0))
    f_kws = ee.String(ee.Algorithms.If(feature.get('F_KWS'), feature.get('F_KWS'), '')).trim().toUpperCase()
    pippib = ee.String(ee.Algorithms.If(feature.get('PIPPIB'), feature.get('PIPPIB'), '')).trim().toUpperCase()
    feg = ee.String(ee.Algorithms.If(feature.get('feg_kghltr'), feature.get('feg_kghltr'), '')).trim()
    tuplah = ee.Number(ee.Algorithms.If(feature.get('PL2024_ID'), feature.get('PL2024_ID'), 0))
    tinggi = ee.Number(ee.Algorithms.If(feature.get('Ketinggian'), feature.get('Ketinggian'), 0))
    spd_sungai = ee.String(ee.Algorithms.If(feature.get('Sungai_Kec'), feature.get('Sungai_Kec'), '')).trim().toUpperCase()
    spd_pantai = ee.String(ee.Algorithms.If(feature.get('Spd_Pantai'), feature.get('Spd_Pantai'), '')).trim().toUpperCase()
    spd_danau = ee.String(ee.Algorithms.If(feature.get('Spd_Danau'), feature.get('Spd_Danau'), '')).trim().toUpperCase()
    rurhl = ee.String(ee.Algorithms.If(feature.get('RURHL'), feature.get('RURHL'), '')).trim().toUpperCase()
    lakris = ee.String(ee.Algorithms.If(feature.get('KRITIS'), feature.get('KRITIS'), '')).trim().toUpperCase()
    sawit_val = ee.Number(ee.Algorithms.If(feature.get('SAWIT'), feature.get('SAWIT'), 0))

    is_hl = to_num(f_kws.compareTo('HL').eq(0)).add(to_num(f_kws.compareTo('HUTAN LINDUNG').eq(0))).gt(0)
    ruang = ee.String(ee.Algorithms.If(is_hl, 'Perlindungan', 'Pemanfaatan'))
    current_set = ee.List(ee.Algorithms.If(is_hl, ['A1', 'A2', 'A4'], ['A1', 'A2', 'A3', 'A4', 'A5']))
    is_gambut = to_num(pippib.match('GAMBUT|KAWASAN').length().gt(0)).eq(1)
    current_set = ee.List(ee.Algorithms.If(is_gambut, current_set.filter(ee.Filter.inList('item', ['A1', 'A2', 'A3', 'A4'])), current_set))
    is_lindung_eg = to_num(feg.compareTo('Indikatif Fungsi Lindung E.G.').eq(0)).eq(1)
    is_budidaya_eg = to_num(feg.compareTo('Indikatif Fungsi Budidaya E.G.').eq(0)).eq(1)
    ruang = ee.String(ee.Algorithms.If(is_lindung_eg, 'Perlindungan', ruang))
    current_set = ee.List(ee.Algorithms.If(is_lindung_eg, ['A6'], ee.Algorithms.If(is_budidaya_eg, current_set.filter(ee.Filter.inList('item', ['A1', 'A2', 'A3', 'A4'])), current_set)))
    list_constraint = ee.List(ee.Algorithms.If(is_hl, ['A2', 'A4'], ['A1', 'A2', 'A3', 'A4']))
    list_tuplah = ee.List([2001, 2002, 2004, 2005, 20041, 20051])
    is_trigger = to_num(list_tuplah.contains(tuplah)).add(to_num(tinggi.eq(2000))).add(to_num(spd_sungai.compareTo('YA').eq(0))).add(to_num(spd_pantai.compareTo('YA').eq(0))).add(to_num(spd_danau.compareTo('YA').eq(0))).gt(0)
    ruang = ee.String(ee.Algorithms.If(is_trigger, 'Perlindungan', ruang))
    current_set = ee.List(ee.Algorithms.If(is_trigger, current_set.filter(ee.Filter.inList('item', list_constraint)), current_set))
    str_arahan = ee.List(ee.Algorithms.If(current_set.length().eq(0), ['A6'], current_set)).sort().join('')
    list_kewajiban = ee.List([])
    is_k2 = to_num(is_lindung_eg).add(to_num(is_budidaya_eg)).gt(0)
    list_kewajiban = ee.List(ee.Algorithms.If(is_k2, list_kewajiban.add('K2'), list_kewajiban))
    is_k3 = to_num(rurhl.compareTo('RURHL').eq(0)).add(to_num(lakris.match('KRITIS').length().gt(0))).gt(0)
    list_kewajiban = ee.List(ee.Algorithms.If(is_k3, list_kewajiban.add('K3'), list_kewajiban))
    list_kewajiban = ee.List(ee.Algorithms.If(sawit_val.eq(1), list_kewajiban.add('K1'), list_kewajiban))
    return feature.set({'Arahan': str_arahan, 'Kewajiban': list_kewajiban.sort().join(''), 'Ruang': ruang})

# =========================================================
# 5. EKSEKUSI
# =========================================================
col1, col2 = st.columns([1, 2])

with col1:
    st.markdown("### 📁 Panel Input")
    selected_prov_name = st.selectbox("Pilih Wilayah Kerja:", list(ASSET_MAPPING.keys()))
    uploaded_file = st.file_uploader("Upload File SHP (.ZIP)", type="zip", help="File harus berisi .shp, .shx, .dbf, .prj")

if uploaded_file and st.button("🚀 JALANKAN ANALISIS", type="primary"):
    with col2:
        status = st.status("Memproses data...", expanded=True)
        try:
            status.write("⚙️ Membersihkan geometri input...")
            user_geom = get_sanitized_geometry(uploaded_file)
            
            asset_suffix = ASSET_MAPPING[selected_prov_name]
            asset_path = f"projects/papaps/assets/PAPAPS_{asset_suffix}"
            
            status.write(f"🛰️ Mengakses data Asset: {asset_suffix}...")
            union_tematik = ee.FeatureCollection(asset_path)
            
            clipped = union_tematik.filterBounds(user_geom).map(lambda f: f.intersection(user_geom, 1))
            processed = clipped.map(lambda f: f.set('SAWIT', 0))
            calculated = processed.map(calculate_attributes)
            
            status.write("📐 Menghitung luas (CEA)...")
            wkt_cea = 'PROJCS["World_Cylindrical_Equal_Area",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],PROJECTION["Cylindrical_Equal_Area"],PARAMETER["False_Easting",0],PARAMETER["False_Northing",0],PARAMETER["Central_Meridian",0],PARAMETER["Standard_Parallel_1",0],UNIT["Meter",1]]'
            final_fc = calculated.map(lambda f: f.setGeometry(f.geometry().buffer(0.1, 1))).map(lambda f: f.set('luas_ha', f.geometry().area(1, wkt_cea).divide(10000)))
            
            status.write("📥 Mengunduh hasil...")
            gdf_raw = geemap.ee_to_gdf(final_fc.select(['Arahan', 'Kewajiban', 'Ruang', 'luas_ha']))
            
            if gdf_raw.empty:
                status.update(label="Selesai, namun tidak ada data.", state="warning", expanded=False)
                st.warning("Area input tidak beririsan dengan data Arahan di wilayah ini.")
            else:
                status.write("🧩 Melakukan Dissolve dan formatting...")
                dissolved = gdf_raw.dissolve(by=['Arahan', 'Kewajiban', 'Ruang'], aggfunc={'luas_ha': 'sum'}).reset_index()
                dissolved.set_crs("EPSG:4326", inplace=True, allow_override=True)
                
                status.update(label="✅ Analisis Berhasil!", state="complete", expanded=False)
                st.success(f"Analisis Selesai untuk wilayah: {selected_prov_name}")

                st.markdown("### 📊 Rekapitulasi Luas")
                st.dataframe(dissolved.drop(columns=['geometry']), use_container_width=True)
                
                out_dir = "papaps_result"
                if os.path.exists(out_dir): shutil.rmtree(out_dir)
                os.makedirs(out_dir)
                dissolved.to_file(os.path.join(out_dir, "Result_PAPAPS.shp"))
                shutil.make_archive("PAPAPS_Output", 'zip', out_dir)
                
                with open("PAPAPS_Output.zip", "rb") as f:
                    st.download_button("📥 DOWNLOAD HASIL LENGKAP (.ZIP)", f, "PAPAPS_Output.zip", type="primary")
                
                # PETA (SILENT ERROR)
                try:
                    st.markdown("### 🗺️ Peta Preview")
                    m = geemap.Map()
                    m.centerObject(user_geom, 12)
                    m.addLayer(user_geom, {'color':'black', 'fillColor': '00000000'}, "Batas Area Input")
                    m.addLayer(geemap.gdf_to_ee(dissolved), {'color':'red'}, "Hasil Arahan PAPAPS")
                    m.to_streamlit(height=500)
                except Exception:
                    pass 

        except Exception as e:
            status.update(label="Terjadi Kesalahan!", state="error")
            st.error(f"Detail Error: {e}")
