# streamlit_app.py
import streamlit as st
from pathlib import Path
from typing import List, Optional, Set
from app_core import compute_and_build
import base64

# ------------------------- CONFIG -------------------------
LOGO_PATH = Path("assets/bau_logo.png")  # Logonuzu bu yola ekleyin
CITESCORE_DIR_CANDIDATES = [Path("CiteScore 2024"), Path(".")]
CITESCORE_FILE_CANDIDATES = [
	"CiteScore 2024 annual values.csv",
	"CiteScore 2024 annual values.xlsx",
	"CiteScore 2024.csv",
	"citescore.csv",
	"citescore.xlsx",
]
DEFAULT_FIXED_YEARS: Optional[Set[int]] = None  # None = Last 3 years, {2022,2023,2024} sabit penceredir

# BAU light renk paleti
BAU_PRIMARY = "#0C2340"    # Navy
BAU_SECONDARY = "#BA0C2F"  # Red
BAU_BG = "#FFFFFF"
BAU_TEXT = "#0C2340"
BAU_SURFACE = "#F6F8FC"

def _find_citescore_path() -> Optional[Path]:
	for d in CITESCORE_DIR_CANDIDATES:
		if d.exists() and d.is_dir():
			for name in CITESCORE_FILE_CANDIDATES:
				p = d / name
				if p.exists() and p.is_file():
					return p
	raw = st.session_state.get("citescore_absolute_path", "")
	if raw:
		p = Path(raw)
		if p.exists() and p.is_file():
			return p
	return None

def get_base64_image(image_path):
	"""Convert image to base64 for embedding in HTML"""
	try:
		with open(image_path, "rb") as img_file:
			return base64.b64encode(img_file.read()).decode()
	except Exception:
		return None

st.set_page_config(page_title="APP Score Calculator", page_icon="📊", layout="centered")

st.markdown(f"""
	<style>
		/* Ana arka plan - gönderdiğiniz görseldeki gibi akışkan gradyan */
		html, body, [class*="css"], .main {{
			background: 
				radial-gradient(circle at 20% 20%, #00FF7F 0%, transparent 50%),
				radial-gradient(circle at 80% 20%, #FF69B4 0%, transparent 50%),
				radial-gradient(circle at 40% 60%, #40E0D0 0%, transparent 50%),
				radial-gradient(circle at 60% 80%, #9370DB 0%, transparent 50%),
				radial-gradient(circle at 10% 80%, #00CED1 0%, transparent 50%),
				linear-gradient(135deg, #00FF7F 0%, #40E0D0 25%, #FF69B4 50%, #9370DB 75%, #00CED1 100%) !important;
			color: {BAU_TEXT} !important;
			min-height: 100vh !important;
		}}
		
		/* Tüm sayfa arka planını akışkan gradyan yap */
		.stApp {{
			background: 
				radial-gradient(circle at 20% 20%, #00FF7F 0%, transparent 50%),
				radial-gradient(circle at 80% 20%, #FF69B4 0%, transparent 50%),
				radial-gradient(circle at 40% 60%, #40E0D0 0%, transparent 50%),
				radial-gradient(circle at 60% 80%, #9370DB 0%, transparent 50%),
				radial-gradient(circle at 10% 80%, #00CED1 0%, transparent 50%),
				linear-gradient(135deg, #00FF7F 0%, #40E0D0 25%, #FF69B4 50%, #9370DB 75%, #00CED1 100%) !important;
		}}
		
		/* Header'ı tamamen kaldır */
		header[data-testid="stHeader"] {{ 
			height: 0px !important;
			display: none !important;
			visibility: hidden !important;
		}}
		
		/* Toolbar'ı gizle */
		header [data-testid="stToolbar"] {{ 
			display: none !important;
		}}
		
		/* Menu'yu gizle */
		#MainMenu {{ 
			visibility: hidden !important;
			display: none !important;
		}}
		
		/* Footer'ı gizle */
		footer {{ 
			visibility: hidden !important;
			display: none !important;
		}}
		
		/* Ana container */
		.block-container {{ 
			padding-top: 0.5rem !important; 
			padding-bottom: 3rem !important; 
			max-width: 960px;
			background: transparent !important;
		}}
		
		/* TÜM YAZILARI BOLD YAP */
		* {{
			font-weight: bold !important;
		}}
		
		/* Ana başlık - koyu lacivert gradyan yansımalı efekt */
		.main-title {{
			color: #0C2340 !important;
			font-size: 3.5rem !important;
			font-weight: bold !important;
			margin-bottom: 0.5rem !important;
			background: linear-gradient(45deg, #0C2340, #1A365D, #2C5282);
			-webkit-background-clip: text;
			-webkit-text-fill-color: transparent;
			background-clip: text;
			text-shadow: 0 4px 8px rgba(12, 35, 64, 0.4) !important;
			filter: drop-shadow(0 2px 4px rgba(12, 35, 64, 0.3));
		}}
		
		/* Logo container - tamamen transparan */
		.logo-container {{
			text-align: center;
			margin-bottom: 1rem;
			padding: 0.5rem 0;
			background: transparent !important;
			background-color: transparent !important;
		}}
		
		/* Logo görüntüleme - tamamen transparan */
		.logo-image {{
			max-height: 140px;
			width: auto;
			margin-bottom: 0.5rem;
			filter: drop-shadow(0 6px 12px rgba(0,0,0,0.2));
			background: transparent !important;
			background-color: transparent !important;
		}}
		
		/* Başlık container - transparan */
		.title-container {{
			text-align: center;
			margin-bottom: 1.5rem;
			background: transparent !important;
			background-color: transparent !important;
		}}
		
		/* Form kartı - şeffaf beyaz arka plan */
		.app-card {{
			background: rgba(255, 255, 255, 0.85) !important;
			border: 1px solid rgba(255, 255, 255, 0.3);
			border-radius: 16px;
			padding: 1.5rem;
			margin-bottom: 1rem;
			box-shadow: 0 8px 32px rgba(0,0,0,0.15);
			backdrop-filter: blur(10px);
		}}
		
		/* TÜM LABEL'LARI BOLD YAP */
		.stTextInput label, .stRadio label, .stExpander label, .stSelectbox label {{
			font-weight: bold !important;
			color: {BAU_PRIMARY} !important;
			font-size: 1.1rem !important;
		}}
		
		/* Input alanları */
		.stTextInput > div > div > input {{
			background-color: rgba(255, 255, 255, 0.9) !important;
			border: 2px solid rgba(12, 35, 64, 0.3) !important;
			border-radius: 8px !important;
			font-weight: bold !important;
			font-size: 1rem !important;
		}}
		
		input:focus, textarea:focus, select:focus {{
			border-color: {BAU_SECONDARY} !important;
			box-shadow: 0 0 0 0.3rem rgba(186, 12, 47, 0.25) !important;
		}}
		
		/* Radio buttonlar */
		.stRadio > div {{
			background-color: rgba(255, 255, 255, 0.8) !important;
			border-radius: 8px;
			padding: 0.5rem;
		}}
		
		.stRadio label {{
			font-weight: bold !important;
			color: {BAU_PRIMARY} !important;
		}}
		
		/* Butonlar */
		.stButton>button {{
			background: linear-gradient(45deg, {BAU_PRIMARY}, {BAU_SECONDARY}) !important;
			color: #FFFFFF !important;
			border: none !important;
			border-radius: 8px !important;
			font-weight: bold !important;
			font-size: 1.2rem !important;
			padding: 0.75rem 2rem !important;
			box-shadow: 0 4px 15px rgba(0,0,0,0.3) !important;
			transition: all 0.3s ease !important;
		}}
		
		.stButton>button:hover {{
			transform: translateY(-2px) !important;
			box-shadow: 0 6px 20px rgba(0,0,0,0.4) !important;
		}}
		
		/* Expander */
		.stExpander {{
			background-color: rgba(255, 255, 255, 0.8) !important;
			border-radius: 8px;
		}}
		
		.stExpander label {{
			font-weight: bold !important;
			color: {BAU_PRIMARY} !important;
		}}
		
		/* Footer */
		.footer-container {{
			text-align: center;
			margin-top: 2rem;
			padding: 1rem;
			color: {BAU_PRIMARY};
			font-weight: bold !important;
			font-size: 1rem;
			background: linear-gradient(45deg, {BAU_PRIMARY}, {BAU_SECONDARY});
			-webkit-background-clip: text;
			-webkit-text-fill-color: transparent;
			background-clip: text;
		}}
		
		/* Success/Error mesajları */
		.stSuccess {{
			background-color: rgba(76, 175, 80, 0.15) !important;
			border: 1px solid rgba(76, 175, 80, 0.4) !important;
			font-weight: bold !important;
		}}
		
		.stError {{
			background-color: rgba(244, 67, 54, 0.15) !important;
			border: 1px solid rgba(244, 67, 54, 0.4) !important;
			font-weight: bold !important;
		}}
		
		/* Metric */
		.stMetric {{
			background-color: rgba(255, 255, 255, 0.9) !important;
			border-radius: 12px;
			padding: 1rem;
			box-shadow: 0 4px 15px rgba(0,0,0,0.15);
		}}
		
		/* Caption */
		.stCaption {{
			font-weight: bold !important;
			color: {BAU_PRIMARY} !important;
		}}
		
		/* Write text */
		.stWrite {{
			font-weight: bold !important;
		}}
		
		/* Placeholder text */
		input::placeholder {{
			font-weight: bold !important;
			color: rgba(12, 35, 64, 0.6) !important;
		}}
		
		/* Logo için özel stil - tamamen transparan */
		.logo-container img {{
			background: transparent !important;
			background-color: transparent !important;
		}}
		
		/* Tüm beyaz arka planları kaldır */
		.stApp > div {{
			background: transparent !important;
		}}
		
		/* Streamlit'in varsayılan beyaz arka planlarını kaldır */
		.stApp > div > div {{
			background: transparent !important;
		}}
	</style>
""", unsafe_allow_html=True)

# Logo ve başlık bölümü - tamamen transparan
logo_base64 = get_base64_image(LOGO_PATH) if LOGO_PATH.exists() else None

if logo_base64:
	st.markdown(f"""
		<div class="logo-container">
			<img src="data:image/png;base64,{logo_base64}" class="logo-image" alt="BAU Logo" style="background: transparent !important; background-color: transparent !important;">
		</div>
	""", unsafe_allow_html=True)
else:
	st.markdown('<div class="logo-container"><div style="height: 140px; background: transparent !important;"></div></div>', unsafe_allow_html=True)

# Ana başlık - koyu lacivert gradyan yansımalı
st.markdown("""
	<div class="title-container">
		<h1 class="main-title">APP Score Calculator</h1>
	</div>
""", unsafe_allow_html=True)

with st.form("app_form"):
	st.markdown('<div class="app-card">', unsafe_allow_html=True)
	auids_text = st.text_input("Scopus Author ID(s)", placeholder="57193254610, 55042518500 ...")
	aff_id = st.text_input("Optional Affiliation ID (default BAU: 60021379)", value="")
	year_mode = st.radio("Year window", ["Last 3 years", "Fixed: 2022-2024"], index=(0 if DEFAULT_FIXED_YEARS is None else 1), horizontal=True)
	with st.expander("Advanced (optional)"):
		st.write("CiteScore file is auto-detected from the project folder. If needed, enter an absolute path below:")
		st.text_input("Absolute path to CiteScore CSV/XLSX (optional)", key="citescore_absolute_path", placeholder=r"C:\path\to\CiteScore 2024 annual values.csv")
	st.markdown("</div>", unsafe_allow_html=True)
	submitted = st.form_submit_button("Calculate")

if submitted:
	if not auids_text.strip():
		st.error("Please enter at least one Scopus Author ID (AU-ID).")
	else:
		auids: List[str] = []
		for tok in [t.strip() for t in auids_text.replace(";", ",").split(",")]:
			if tok.isdigit():
				auids.append(tok)
		auids = sorted(set(auids))
		if not auids:
			st.error("No valid AU-ID(s) found.")
		else:
			fixed_years: Optional[Set[int]] = {2022, 2023, 2024} if year_mode.startswith("Fixed") else None
			if DEFAULT_FIXED_YEARS is not None:
				fixed_years = DEFAULT_FIXED_YEARS
			cs_path = _find_citescore_path()
			if not cs_path:
				st.error(
					"Could not locate the CiteScore file automatically.\n\n"
					"Place one of the following files in the project root or 'CiteScore 2024' folder:\n"
					f" - {', '.join(CITESCORE_FILE_CANDIDATES)}\n\n"
					"Or use the 'Advanced' expander to type an absolute path."
				)
			else:
				with st.spinner("Fetching from Scopus and computing APP..."):
					try:
						summary, excel_bytes, filename = compute_and_build(
							auids=auids,
							citescore_path=str(cs_path),
							aff_id=(aff_id.strip() or None),
							sleep=0.05,
							serial_sleep=0.1,
							fixed_years=fixed_years
						)
					except Exception as e:
						st.exception(e)
					else:
						st.success("Completed.")
						st.metric(label="APP Score", value=summary.get("app_total", 0.0))
						st.write("Eligibility:", summary.get("eligibility", ""))
						st.write("Years considered:", ", ".join(map(str, summary.get("years", []))))
						st.caption(f"Using CiteScore file: {cs_path}")
						st.download_button(
							label="Download Excel",
							data=excel_bytes,
							file_name=filename,
							mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
						)

# Footer - Bahçeşehir Üniversitesi bilgisi
st.markdown("""
	<div class="footer-container">
		<p>Developed by Bahçeşehir University</p>
	</div>
""", unsafe_allow_html=True)