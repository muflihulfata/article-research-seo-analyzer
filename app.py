import re
from copy import deepcopy
from collections import Counter
from urllib.parse import urlparse, urljoin
import requests
import streamlit as st
import trafilatura
from bs4 import BeautifulSoup

st.set_page_config(page_title="Article Research & SEO Analyzer", page_icon="🔎", layout="wide")

STOPWORDS = set("""yang dan di ke dari untuk dengan pada adalah ini itu atau dalam sebagai akan dapat tidak lebih juga agar karena oleh jika saat secara para sebuah seorang suatu menjadi telah sudah masih sangat bisa hanya terhadap antara hingga tanpa serta namun tetapi ada jadi tentang melalui setelah sebelum ketika kami kita mereka anda kamu ia dia the a an and or of to in for on with is are was were be been this that from by as at it its""".split())

def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()

def is_noise_element(tag):
    """Deteksi widget non-artikel seperti rekomendasi, navigasi, dan iklan."""
    marker = " ".join([
        str(tag.get("id", "")),
        " ".join(tag.get("class", [])) if isinstance(tag.get("class", []), list) else str(tag.get("class", "")),
        str(tag.get("aria-label", "")),
        str(tag.get("role", "")),
    ]).lower()
    return bool(re.search(
        r"related|recommend|popular|trending|breadcrumb|sidebar|advert|ads|"
        r"newsletter|comment|social|share|tag-list|topic-list|terkait|terpopuler|"
        r"baca-juga|artikel-lain|most-read|more-stories",
        marker
    ))

def is_noise_heading(text):
    t = clean_text(text).lower()
    if not t:
        return True
    patterns = [
        r"^(topik terkait|artikel terkait|baca juga|berita terkait|berita lainnya)$",
        r"^(mom'?s life|haibunda|terpopuler|paling banyak dibaca)$",
        r"^(foto|infografis|advertorial)$",
        r"^di balik .+ menurut psikologi$",
    ]
    return any(re.search(p, t) for p in patterns)

def fetch_article(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ArticleResearchSEOAnalyzer/1.1)"}
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError("URL tidak mengarah ke halaman HTML.")
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = clean_text(title_tag.get("content", "") if title_tag and title_tag.name == "meta" else title_tag.get_text(" ", strip=True) if title_tag else "")
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)}) or soup.find("meta", property="og:description")
    meta_desc = clean_text(md.get("content", "")) if md else ""
    canonical = soup.find("link", rel="canonical")
    canonical_url = canonical.get("href", "") if canonical else ""

    # Pilih kontainer artikel, bukan seluruh halaman. Salinan dipakai agar
    # penghapusan widget tidak mengubah dokumen sumber untuk metadata.
    selectors = [
        '[itemprop="articleBody"]', "article", "main",
        '[class*="article-content"]', '[class*="article__content"]',
        '[class*="detail-content"]', '[class*="content-article"]'
    ]
    candidates = []
    for selector in selectors:
        try:
            candidates.extend(soup.select(selector))
        except Exception:
            pass
    candidates = list(dict.fromkeys(candidates))
    root = max(
        candidates,
        key=lambda x: (len(x.find_all("p")) * 100) + len(x.get_text(" ", strip=True)),
        default=None
    )
    article_root = deepcopy(root) if root else None

    headings = []
    images = []
    image_alts = []
    links = []
    host = urlparse(url).netloc.lower()

    if article_root:
        for node in list(article_root.find_all(True)):
            if is_noise_element(node):
                node.decompose()
        for tag in article_root.find_all(re.compile(r"^h[1-6]$")):
            txt = clean_text(tag.get_text(" ", strip=True))
            # Hindari heading rekomendasi/metadata dan heading di widget terkait.
            if txt and not is_noise_heading(txt) and len(txt) < 180:
                headings.append((tag.name.upper(), txt))
        images = article_root.find_all("img")
        image_alts = [clean_text(i.get("alt", "")) for i in images]
        for a in article_root.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if urlparse(href).scheme in ("http", "https"):
                links.append((clean_text(a.get_text(" ", strip=True)), href, urlparse(href).netloc.lower() == host))

        # Bangun teks dari paragraf dan subheading di kontainer artikel saja.
        blocks = []
        for node in article_root.find_all(["h2", "h3", "h4", "p", "blockquote", "li"]):
            if any(is_noise_element(parent) for parent in node.parents if parent is not article_root):
                continue
            txt = clean_text(node.get_text(" ", strip=True))
            if not txt or is_noise_heading(txt):
                continue
            if node.name == "li" and len(txt.split()) < 4:
                continue
            if txt not in blocks:
                blocks.append(txt)
        body = "\n\n".join(blocks)
    else:
        body = ""

    # Fallback ke Trafilatura jika struktur HTML tidak menyediakan kontainer artikel.
    if len(body) < 250:
        extracted = trafilatura.extract(
            html, url=url, include_comments=False, include_tables=False,
            favor_recall=True, deduplicate=True
        )
        if extracted and len(extracted.strip()) > len(body):
            body = clean_text(extracted)
    if not headings:
        # Jangan mengambil heading global halaman: gunakan heading dari hasil ekstraksi bila tersedia.
        headings = []
        if article_root:
            for tag in article_root.find_all(re.compile(r"^h[1-6]$")):
                txt = clean_text(tag.get_text(" ", strip=True))
                if txt and not is_noise_heading(txt):
                    headings.append((tag.name.upper(), txt))

    return {
        "title": title, "description": meta_desc, "canonical": canonical_url,
        "headings": headings, "body": body, "images": images,
        "image_alts": image_alts, "links": links, "status": response.status_code
    }

def keywords(text, n=15):
    words = re.findall(r"(?u)\b[\w-]{3,}\b", text.lower())
    words = [w for w in words if w not in STOPWORDS and not w.isdigit()]
    return Counter(words).most_common(n)

def intent_guess(title, body):
    t = (title + " " + body[:1800]).lower()
    if re.search(r"\b(harga|review|terbaik|rekomendasi|vs|perbandingan|beli|produk)\b", t):
        return "Komersial / investigasi komersial", "Ada sinyal evaluasi produk, perbandingan, rekomendasi, atau keputusan pembelian."
    if re.search(r"\b(cara|tips|tutorial|panduan|langkah|apa itu|mengapa|bagaimana)\b", t):
        return "Informasional", "Judul atau isi mengarah pada penjelasan, panduan, atau pemecahan masalah."
    if re.search(r"\b(login|masuk|daftar|website resmi|situs resmi)\b", t):
        return "Navigasional", "Ada sinyal pencarian menuju situs atau layanan tertentu."
    return "Belum dapat dipastikan (kemungkinan informasional)", "Klasifikasi otomatis berbasis kata pemicu; periksa kembali kebutuhan pencarian audiens."

def score_article(data):
    title, desc, body = data["title"], data["description"], data["body"]
    words = re.findall(r"(?u)\b[\w-]+\b", body)
    headings = data["headings"]
    h1 = [x for x in headings if x[0] == "H1"]
    checks = [
        ("Judul halaman tersedia", bool(title), "Tambahkan elemen title yang spesifik."),
        ("Meta description tersedia", bool(desc), "Tulis meta description unik yang merangkum manfaat halaman."),
        ("H1 tersedia", bool(h1), "Tambahkan satu H1 yang menggambarkan topik utama."),
        ("Konten cukup panjang (≥600 kata)", len(words) >= 600, "Perluas pembahasan jika topik memang membutuhkan kedalaman."),
        ("Struktur subjudul tersedia", any(x[0] in ("H2","H3") for x in headings), "Bagi artikel dengan H2/H3 yang deskriptif."),
        ("Gambar memiliki alt", bool(data["images"]) and all(a for a in data["image_alts"]), "Isi alt text deskriptif pada gambar yang informatif."),
        ("Tautan internal tersedia", any(x[2] for x in data["links"]), "Tambahkan tautan internal relevan bila mendukung navigasi."),
    ]
    score = round(sum(ok for _, ok, _ in checks) / len(checks) * 100)
    return score, checks

st.title("🔎 Article Research & SEO Analyzer")
st.caption("Analisis artikel berbasis URL: ekstraksi konten, riset topik, pemeriksaan on-page SEO, dan rekomendasi.")
st.info("Gratis digunakan tanpa akun. Analisis dibuat dengan ekstraksi halaman dan aturan heuristik—bukan skor resmi Google atau pengganti audit SEO profesional.")

url = st.text_input("URL artikel", placeholder="https://contoh.com/judul-artikel")
analyze = st.button("Analisis Artikel", type="primary", use_container_width=True)

if analyze:
    if not url.strip():
        st.error("Masukkan URL artikel terlebih dahulu.")
    else:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            st.error("Masukkan URL lengkap yang diawali http:// atau https://.")
        else:
            with st.spinner("Mengambil dan menganalisis artikel..."):
                try:
                    data = fetch_article(url.strip())
                    if len(data["body"]) < 120:
                        st.warning("Halaman berhasil dibuka, tetapi teks artikel yang dapat diekstrak sangat sedikit. Situs mungkin memakai JavaScript, paywall, atau proteksi bot.")
                    else:
                        st.session_state["analysis"] = data
                        st.session_state["analyzed_url"] = url.strip()
                except requests.exceptions.Timeout:
                    st.error("Waktu akses habis. Coba lagi atau gunakan URL artikel lain.")
                except requests.exceptions.RequestException as e:
                    st.error(f"Tidak dapat mengambil halaman: {e}")
                except Exception as e:
                    st.error(f"Analisis gagal: {e}")

if "analysis" in st.session_state:
    d = st.session_state["analysis"]
    body = d["body"]
    words = re.findall(r"(?u)\b[\w-]+\b", body)
    kw = keywords(body)
    score, checks = score_article(d)
    intent, intent_reason = intent_guess(d["title"], body)
    st.divider()
    st.subheader("Ringkasan hasil")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Skor pemeriksaan SEO", f"{score}/100")
    c2.metric("Jumlah kata", f"{len(words):,}")
    c3.metric("Subjudul", sum(1 for h,_ in d["headings"] if h in ("H2","H3")))
    c4.metric("Tautan terdeteksi", len(d["links"]))
    st.markdown("### Identitas artikel")
    st.write("**URL:**", st.session_state["analyzed_url"])
    st.write("**Title:**", d["title"] or "Tidak terdeteksi")
    st.write("**Meta description:**", d["description"] or "Tidak terdeteksi")
    st.write("**Canonical:**", d["canonical"] or "Tidak terdeteksi")
    st.markdown("### Inti artikel")
    st.write(body[:1300] + ("..." if len(body)>1300 else ""))
    if len(body) > 1300:
        with st.expander("Lihat seluruh teks artikel yang berhasil diekstrak"):
            st.text(body)
    st.caption("Pratinjau di atas dibatasi 1.300 karakter untuk tampilan. Buka bagian ini untuk memeriksa teks lengkap hasil ekstraksi.")
    st.markdown("### Search intent (perkiraan)")
    st.write(f"**{intent}.** {intent_reason}")
    st.markdown("### Kata kunci")
    if kw:
        st.dataframe([{"Kata/frasa": k, "Frekuensi": v} for k,v in kw], use_container_width=True, hide_index=True)
    st.caption("Kata kunci versi ini masih berupa frekuensi kata tunggal, bukan volume pencarian atau riset keyword kompetitif. Tahap berikutnya adalah peningkatan analisis frasa dan relevansi semantik.")
    st.markdown("### Struktur heading artikel")
    st.caption("Heading diambil dari kontainer artikel yang terdeteksi; widget rekomendasi dan topik terkait disaring sejauh dapat dikenali dari struktur HTML situs.")
    if d["headings"]:
        for level, heading in d["headings"]:
            st.write(f"{'　' * (int(level[1])-1)}**{level}** — {heading}")
    else:
        st.write("Tidak ditemukan heading H1–H6.")
    st.markdown("### Pemeriksaan SEO on-page")
    for label, ok, fix in checks:
        st.write(("✅ " if ok else "⚠️ ") + label + ("" if ok else " — " + fix))
    st.markdown("### Kualitas dan peluang pengembangan")
    paragraphs = [p for p in re.split(r"(?<=[.!?])\s+", body) if len(p.split()) > 5]
    avg_sentence = round(len(words)/max(1,len(paragraphs)),1)
    st.write(f"- Perkiraan rata-rata kata per kalimat: **{avg_sentence}** (indikator kasar).")
    st.write(f"- Gambar ditemukan: **{len(d['images'])}**; gambar tanpa alt: **{sum(not a for a in d['image_alts'])}**.")
    st.write(f"- Tautan internal: **{sum(1 for x in d['links'] if x[2])}**; tautan eksternal: **{sum(1 for x in d['links'] if not x[2])}**.")
    st.write("- Content gap belum dibandingkan otomatis dengan halaman pesaing. Gunakan heading dan keyword sebagai petunjuk untuk mengecek subtopik yang belum dibahas.")
    st.markdown("### Rekomendasi prioritas")
    recommendations = [fix for _,ok,fix in checks if not ok]
    if recommendations:
        for r in recommendations:
            st.write("- " + r)
    else:
        st.write("Pemeriksaan dasar terpenuhi. Selanjutnya evaluasi akurasi, orisinalitas, sumber rujukan, pengalaman langsung, dan kesesuaian dengan search intent.")
    st.markdown("### Ekspor hasil")
    report = f"""ARTICLE RESEARCH & SEO ANALYSIS\nURL: {st.session_state['analyzed_url']}\nTITLE: {d['title']}\nMETA DESCRIPTION: {d['description']}\nSEO CHECK SCORE: {score}/100\nWORD COUNT: {len(words)}\nSEARCH INTENT: {intent}\n\nTOP KEYWORDS:\n""" + "\n".join(f"- {k}: {v}" for k,v in kw) + "\n\nHEADINGS:\n" + "\n".join(f"- {a}: {b}" for a,b in d["headings"]) + "\n\nRECOMMENDATIONS:\n" + "\n".join(f"- {x}" for x in recommendations) + "\n\nARTICLE TEXT:\n" + body
    st.download_button("Unduh laporan TXT", report, file_name="laporan_article_seo.txt", mime="text/plain")

with st.expander("Catatan penggunaan dan batasan"):
    st.markdown("""
    - Aplikasi tidak membutuhkan API berbayar atau kunci API.
    - Beberapa situs menolak permintaan otomatis, membatasi akses, menggunakan JavaScript berat, atau memasang paywall. Dalam kasus tersebut ekstraksi dapat gagal/tidak lengkap.
    - Search intent, kata kunci, dan skor adalah estimasi otomatis. Aplikasi ini tidak mengambil volume keyword, ranking Google, backlink, atau data Search Console.
    - Gunakan hanya untuk halaman yang boleh Anda akses dan analisis.
    """)
