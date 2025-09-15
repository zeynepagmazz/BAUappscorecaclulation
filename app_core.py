from __future__ import annotations
import io, os, re, time, json, warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import pandas as pd

from pybliometrics.scopus import AbstractRetrieval, AuthorRetrieval, ScopusSearch, SerialTitle
from pybliometrics.scopus.exception import ScopusException

AFF_ID_DEFAULT = "60021379" 


def _s(x) -> str:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
    except Exception:
        pass
    return x if isinstance(x, str) else str(x)

def _norm_issn(s: str) -> str:
    return re.sub(r"[^0-9X]", "", _s(s).upper())

def _norm_asjc_codes(raw: Any) -> Set[str]:
    out: Set[str] = set()
    if raw is None: return out
    it = raw if isinstance(raw, (list, tuple, set)) else re.split(r"[^0-9]", _s(raw))
    for tok in it:
        if tok and tok.isdigit():
            out.add(tok[-4:] if len(tok) > 4 else tok if len(tok) == 4 else tok)
    return {t for t in out if len(t) == 4}

def _coerce_percentile(val) -> Optional[float]:
    txt = _s(val).strip().replace("%","").replace(" ","").replace(",",".")
    if not txt: return None
    m = re.search(r"[-+]?\d*\.?\d+", txt)
    return float(m.group(0)) if m else None

def _coerce_float(val) -> Optional[float]:
    txt = _s(val).strip().replace(",",".")
    if not txt: return None
    m = re.search(r"[-+]?\d*\.?\d+", txt)
    return float(m.group(0)) if m else None

def quartile_from_percentile(p: Optional[float]) -> str:
    if p is None: return ""
    try: p = float(p)
    except Exception: return ""
    if p >= 90: return "QT"
    if p >= 75: return "Q1"
    if p >= 50: return "Q2"
    if p >= 25: return "Q3"
    return "Q4"

def _to_int_year(y: Any) -> Optional[int]:
    try:
        m = re.search(r"\d{4}", str(y))
        return int(m.group(0)) if m else None
    except Exception:
        return None

def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None

def robust_read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CiteScore file not found: {path}")
    if path.suffix.lower() in (".xlsx",".xls"):
        return pd.read_excel(path)
    encodings = ["utf-8-sig","utf-16","utf-16le","utf-16be","cp1254","iso-8859-9","cp1252","latin1"]
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, engine="python", sep=None)
        except Exception:
            continue
    try:
        return pd.read_csv(path, encoding="latin1", engine="python", sep=None, on_bad_lines="skip")
    except TypeError:
        return pd.read_csv(path, encoding="latin1", engine="python", sep=None, error_bad_lines=False)  # type: ignore

def load_citescore_table(path: Path) -> pd.DataFrame:
    cs = robust_read_table(path)
    norm = {c.strip().lower(): c for c in cs.columns}

    p = norm.get("print issn") or norm.get("p-issn") or norm.get("issn")
    e = norm.get("e-issn") or norm.get("eissn")
    pct = norm.get("percentile") or norm.get("citescore percentile")
    val = norm.get("citescore") or norm.get("citescore 2024")
    src = norm.get("source id") or norm.get("scopus source id") or norm.get("scopus sourceid")
    asjc_col = norm.get("asjc") or norm.get("asjc code") or norm.get("asjc codes") or norm.get("subject area asjc")
    if not all([p, e, pct, val]):
        raise KeyError(f"CiteScore tablosunda 'Print ISSN','E-ISSN','Percentile','CiteScore' zorunlu. Sütunlar: {list(cs.columns)}")

    cs = cs.rename(columns={p:"print_issn", e:"e_issn", pct:"cs_percentile", val:"citescore"})
    if src: cs = cs.rename(columns={src:"source_id"})
    cs["asjc_raw"] = cs[asjc_col] if asjc_col else ""

    cs["print_issn"] = cs["print_issn"].astype(str)
    cs["e_issn"] = cs["e_issn"].astype(str)
    cs["cs_percentile"] = cs["cs_percentile"].apply(_coerce_percentile)
    cs["citescore"] = cs["citescore"].apply(_coerce_float)
    if "source_id" in cs.columns:
        cs["source_id"] = cs["source_id"].astype(str).str.extract(r"(\d+)", expand=False).fillna("")

    cs["issn_key"] = cs["print_issn"].map(_norm_issn)
    cs["eissn_key"] = cs["e_issn"].map(_norm_issn)
    cs["asjc_set"] = cs["asjc_raw"].apply(lambda v: frozenset(_norm_asjc_codes(v)))

    keep = ["issn_key","eissn_key","asjc_set","cs_percentile","citescore"]
    if "source_id" in cs.columns: keep.insert(0,"source_id")
    return cs[keep]

def fetch_source_id_for_issn(issn: str) -> Optional[str]:
    issn = _norm_issn(issn)
    if not issn: return None
    try:
        res = SerialTitle(issn)
        items: Iterable[Any]
        try: items = list(res) if isinstance(res, (list, tuple)) else [res]
        except Exception: items = [res]
        for it in items:
            for attr in ("source_id","sourcerecord_id","sourceid"):
                if hasattr(it, attr):
                    sid = _s(getattr(it, attr))
                    if sid.isdigit(): return sid
        return None
    except Exception as e:
        warnings.warn(f"SerialTitle lookup failed for ISSN {issn}: {e}")
        return None

def build_cs_by_source(cs_table: pd.DataFrame, serial_sleep: float = 0.1) -> pd.DataFrame:
    if "source_id" in cs_table.columns:
        df = cs_table.copy()
    else:
        df = cs_table.copy()
        df["source_id_from_print"] = df["issn_key"].apply(fetch_source_id_for_issn)
        if serial_sleep: time.sleep(serial_sleep)
        df["source_id_from_e"] = df["eissn_key"].apply(fetch_source_id_for_issn)
        df["source_id"] = df["source_id_from_print"].where(df["source_id_from_print"].notna(), df["source_id_from_e"])
        df = df.drop(columns=["source_id_from_print","source_id_from_e"], errors="ignore")
    df = df[df["source_id"].astype(str).str.strip().ne("")].copy()
    df = df.drop_duplicates(subset=["source_id","asjc_set"], keep="first")
    return df[["source_id","asjc_set","cs_percentile","citescore"]]

def _extract_issns(ar: Any) -> Tuple[str,str]:
    p = ""; e = ""
    if hasattr(ar,"eIssn"): e = _s(getattr(ar,"eIssn"))
    if not e and hasattr(ar,"e_issn"): e = _s(getattr(ar,"e_issn"))
    if hasattr(ar,"issn"):
        obj = getattr(ar,"issn")
        if isinstance(obj,str):
            if "ISSN(" in obj:
                mp = re.search(r"print\s*=\s*'([^']+)'", obj)
                me = re.search(r"electronic\s*=\s*'([^']+)'", obj)
                if mp: p = mp.group(1)
                if me and not e: e = me.group(1)
            else:
                p = _s(obj)
        else:
            try:
                p_obj = getattr(obj,"print",""); e_obj = getattr(obj,"electronic","")
                if p_obj: p = _s(p_obj)
                if not e and e_obj: e = _s(e_obj)
            except Exception:
                txt = _s(obj)
                mp = re.search(r"print\s*=\s*'([^']+)'", txt)
                me = re.search(r"electronic\s*=\s*'([^']+)'", txt)
                if mp: p = mp.group(1)
                if me and not e: e = me.group(1)
    return p, e

def _extract_asjc(ar: Any) -> Tuple[str,str,str,Set[str]]:
    codes: Set[str] = set(); areas: Set[str] = set(); abbr: Set[str] = set()
    sa = getattr(ar,"subject_areas", None)
    if sa:
        try:
            for it in sa:
                c = getattr(it,"code",None)
                a = getattr(it,"area",None)
                ab = getattr(it,"abbrev",None)
                if c is not None: codes.add(f"{int(c):04d}" if str(c).isdigit() else str(c))
                if a: areas.add(_s(a))
                if ab: abbr.add(_s(ab))
        except Exception:
            pass
    return ", ".join(sorted(codes)), ", ".join(sorted(areas)), ", ".join(sorted(abbr)), codes


def _pick_best_candidate(cands: pd.DataFrame, article_asjc: Set[str]) -> Tuple[Optional[float],Optional[float]]:
    if cands is None or cands.empty: return None, None
    over = []
    for _i, row in cands.iterrows():
        cs_set = row.get("asjc_set") or set()
        if isinstance(cs_set, (set,frozenset)): cs_set2 = set(cs_set)
        elif isinstance(cs_set, (list,tuple)): cs_set2 = {str(x) for x in cs_set}
        else: cs_set2 = _norm_asjc_codes(cs_set)
        over.append(len(article_asjc & cs_set2))
    cands = cands.copy()
    cands["_overlap"] = over
    cands["_pct"] = cands["cs_percentile"].fillna(-1e9)
    cands = cands.sort_values(["_overlap","_pct"], ascending=[False,False])
    top = cands.iloc[0]
    return top.get("cs_percentile"), top.get("citescore")

def enrich_with_citescore_sourceid_asjc(df_articles: pd.DataFrame, cs_table: pd.DataFrame, cs_by_source: pd.DataFrame) -> pd.DataFrame:
    if df_articles is None or df_articles.empty: return df_articles.copy()
    df = df_articles.copy()
    for col in ("issn_print","issn_electronic","source_id"):
        if col not in df.columns: df[col] = ""
    df["issn_key"] = df["issn_print"].astype(str).map(_norm_issn)
    df["eissn_key"] = df["issn_electronic"].astype(str).map(_norm_issn)
    a_asjc_sets: List[Set[str]] = [ _norm_asjc_codes(v) for v in df.get("asjc_codes", pd.Series([""]*len(df))) ]
    cs_p = cs_table[["issn_key","asjc_set","cs_percentile","citescore"]].drop_duplicates()
    cs_e = cs_table[["eissn_key","asjc_set","cs_percentile","citescore"]].drop_duplicates()
    out_pct: List[Optional[float]] = []; out_val: List[Optional[float]] = []
    for idx, row in df.iterrows():
        article_asjc = a_asjc_sets[idx] if idx < len(a_asjc_sets) else set()
        sid = _s(row.get("source_id"))
        pct = None; val = None
        if sid:
            cands = cs_by_source[cs_by_source["source_id"].astype(str) == sid]
            pct, val = _pick_best_candidate(cands, article_asjc)
        if pct is None and val is None:
            issn = _s(row.get("issn_key")); eissn = _s(row.get("eissn_key"))
            cands = pd.concat([ cs_p[cs_p["issn_key"]==issn], cs_e[cs_e["eissn_key"]==eissn] ], ignore_index=True)
            pct, val = _pick_best_candidate(cands, article_asjc)
        out_pct.append(pct); out_val.append(val)
    df["cs_percentile"] = out_pct
    df["citescore"] = out_val
    df["quartile"] = df["cs_percentile"].apply(quartile_from_percentile)
    return df

def get_author_name(author_id: str) -> str:
    try:
        ar = AuthorRetrieval(author_id)
        name = f"{_s(ar.given_name)} {_s(ar.surname)}".strip()
        return name or author_id
    except Exception:
        return author_id

def get_author_eids(author_id: str) -> List[str]:
    try:
        s = ScopusSearch(f"AU-ID({author_id})", subscriber=True)
        return s.get_eids() or []
    except Exception as e:
        warnings.warn(f"ScopusSearch failed for AU-ID({author_id}): {e}")
        return []

def get_article_metadata(eid: str, target_auid: Optional[str] = None, aff_id: Optional[str] = None):
    try:
        ar = AbstractRetrieval(eid, view="FULL")
    except ScopusException as e:
        warnings.warn(f"AbstractRetrieval failed for {eid}: {e}")
        return None
    if ar.subtype not in ("ar","re"):
        return None

    is_aff_ok = True
    if aff_id:
        is_aff_ok = False
        groups = getattr(ar, "authorgroup", None)
        if groups:
            for g in groups:
                try:
                    g_auid = str(getattr(g, "auid", "") or "")
                    g_aff = _safe_int(getattr(g, "affiliation_id", None))
                    if target_auid and g_auid == str(target_auid) and g_aff == _safe_int(aff_id):
                        is_aff_ok = True
                        break
                except Exception:
                    continue
    if aff_id and not is_aff_ok:
        return None

    year = _s(getattr(ar,"coverDate",""))[:4] if getattr(ar,"coverDate",None) else ""
    issn_print, issn_elec = _extract_issns(ar)
    asjc_codes_csv, asjc_areas_csv, asjc_abbrevs_csv, _ = _extract_asjc(ar)
    return {
        "eid": _s(eid),
        "title": _s(ar.title),
        "year": _s(year),
        "publication_name": _s(getattr(ar,"publicationName","")),
        "subtype": _s(ar.subtype),
        "doi": _s(getattr(ar,"doi","")),
        "source_id": _s(getattr(ar,"source_id","")),
        "issn_print": _s(issn_print),
        "issn_electronic": _s(issn_elec),
        "asjc_codes": asjc_codes_csv,
        "asjc_areas": asjc_areas_csv,
        "asjc_abbrevs": asjc_abbrevs_csv,
        "authors_count": len(ar.authors) if getattr(ar,"authors",None) else 1,
        "combined": "; ".join([t for t in (getattr(ar,"authkeywords",[]) or []) if _s(t)]),
        "abstract": _s(getattr(ar,"description","")),
    }

def collect_author_articles(author_id: str, aff_id: Optional[str], sleep: float = 0.05) -> pd.DataFrame:
    eids = get_author_eids(author_id)
    recs: List[Dict[str,Any]] = []
    for eid in eids:
        md = get_article_metadata(eid, target_auid=author_id, aff_id=aff_id)
        if md: recs.append(md)
        if sleep: time.sleep(sleep)
    return pd.DataFrame(recs)

def _qc_from_percentile(p: Optional[float]) -> Optional[float]:
    if p is None: return None
    try: p = float(p)
    except Exception: return None
    if p >= 90: return 1.4
    if p >= 75: return 1.0
    if p >= 50: return 0.8
    if p >= 25: return 0.6
    if p >= 0:  return 0.4
    return None

def _ac_from_authors(n: Any) -> float:
    try: n = int(n)
    except Exception: n = 1
    return 1.2 if n <= 1 else 1.2 / max(n, 1)

def build_app_sheet(df_articles: pd.DataFrame, fixed_years: Optional[Set[int]] = None) -> Tuple[pd.DataFrame, Dict[str,Any]]:
    if df_articles is None or df_articles.empty:
        return pd.DataFrame(), {"app_total": 0.0, "eligibility": "No eligible items", "years": []}

    if fixed_years:
        years_ok = set(fixed_years)
    else:
        from datetime import datetime
        cy = datetime.now().year
        years_ok = {cy, cy-1, cy-2}

    tmp = df_articles.copy()
    tmp["year_i"] = tmp.get("year","").apply(_to_int_year)
    tmp["cs_percentile_num"] = pd.to_numeric(tmp.get("cs_percentile"), errors="coerce")
    tmp["authors_count_i"] = pd.to_numeric(tmp.get("authors_count"), errors="coerce").fillna(1).astype(int)
    tmp["subtype_norm"] = tmp.get("subtype","").astype(str).str.lower()

    eligible = tmp[tmp["year_i"].isin(years_ok) & tmp["cs_percentile_num"].notna() & (tmp["subtype_norm"]=="ar")].copy()
    if eligible.empty:
        return pd.DataFrame(), {"app_total": 0.0, "eligibility": "No eligible items", "years": sorted(years_ok)}

    eligible["QC"] = eligible["cs_percentile_num"].apply(_qc_from_percentile)
    eligible["AC"] = eligible["authors_count_i"].apply(_ac_from_authors)
    eligible = eligible[eligible["QC"].notna()].copy()
    if eligible.empty:
        return pd.DataFrame(), {"app_total": 0.0, "eligibility": "No eligible items (QC missing)", "years": sorted(years_ok)}

    eligible["Contribution"] = (eligible["AC"] * eligible["QC"]).round(2)
    eligible["AC"] = eligible["AC"].round(2)
    eligible["QC"] = eligible["QC"].round(2)

    out_cols = ["eid","title","year","publication_name","authors_count","cs_percentile","quartile","AC","QC","Contribution"]
    for c in out_cols:
        if c not in eligible.columns: eligible[c] = pd.Series(dtype="object")
    df_app = eligible[out_cols].sort_values(["year","Contribution"], ascending=[False, False]).reset_index(drop=True)

    app_total = float(df_app["Contribution"].sum().round(2))
    if app_total > 1.0:
        elig = "APP > 1.0 → up to 2 supports per academic year (only 1 requires full indexing & APP check)"
    elif app_total >= 0.4:
        elig = "0.4 ≤ APP ≤ 1.0 → 1 support per academic year"
    else:
        elig = "APP < 0.4 → 1 support per academic year (if other criteria met)"

    return df_app, {"app_total": round(app_total, 2), "eligibility": elig, "years": sorted(years_ok)}


def compute_and_build(
    auids: List[str],
    citescore_path: str,
    aff_id: Optional[str] = None,         
    sleep: float = 0.05,
    serial_sleep: float = 0.1,
    fixed_years: Optional[Set[int]] = None
) -> Tuple[Dict[str,Any], bytes, str]:
    # Varsayılanı BAU yap
    if aff_id is None:
        aff_id = AFF_ID_DEFAULT

    cs_path = Path(citescore_path)
    cs_table = load_citescore_table(cs_path)
    cs_by_source = build_cs_by_source(cs_table, serial_sleep=serial_sleep)

    all_rows: List[pd.DataFrame] = []
    for au in auids:
        df = collect_author_articles(au, aff_id=aff_id, sleep=sleep)
        if not df.empty:
            df = enrich_with_citescore_sourceid_asjc(df, cs_table, cs_by_source)
            df["author_id"] = au
            df["author_name"] = get_author_name(au)
            all_rows.append(df)

    merged = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()

    app_df, app_summary = build_app_sheet(merged, fixed_years=fixed_years)

    out_name = "app_results.xlsx"
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
        (merged if not merged.empty else pd.DataFrame()).to_excel(xl, sheet_name="Articles", index=False)
        if not app_df.empty:
            app_df.to_excel(xl, sheet_name="APP", index=False, startrow=5)
            ws = xl.sheets["APP"]
            ws.write(0,0,"APP calculation — journal articles (subtype == 'ar')")
            ws.write(1,0,"Years considered"); ws.write(1,1, ", ".join(str(y) for y in app_summary.get("years",[])))
            ws.write(2,0,"APP Score"); ws.write(2,1, app_summary.get("app_total",0.0))
            ws.write(3,0,"Eligibility"); ws.write(3,1, app_summary.get("eligibility",""))
    buf.seek(0)
    return app_summary, buf.read(), out_name