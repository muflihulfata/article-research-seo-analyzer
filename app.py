import re
import json
from copy import deepcopy
from collections import Counter
from urllib.parse import urlparse, urljoin
import requests
import streamlit as st
import trafilatura
from bs4 import BeautifulSoup

st.set_page_config(page_title="Article Research & SEO Analyzer", page_icon="🔎", layout="wide")

STOPWORDS = set("""yang dan di ke dari untuk dengan pada adalah ini itu atau dalam sebagai akan dapat tidak lebih juga agar karena oleh jika saat secara para sebuah seorang suatu menjadi telah sudah masih sangat bisa hanya terhadap antara hingga tanpa serta namun tetapi ada jadi tentang melalui setelah sebelum ketika kami kita mereka anda kamu ia dia the a an and or of to in for on with is are was were be been this that from by as at it its""".split())
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ArticleResearchSEOAnalyzer/2.0)"}

def clean_text(value):
    return re.sub(r"\\s+", " ", value or "").strip()

def first_value(values):
    for value in values:
        if value and clean_text(value):
            return clean_text(value)
    return ""

def absolute_image_url(raw, page_url):
    raw = clean_text(raw)
    if not raw or raw.startswith(("data:", "blob:", "javascript:")):
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    result = urljoin(page_url, raw)
    return result if urlparse(result).scheme in ("http", "https") else ""

def best_srcset(value):
    if not value:
        return ""
    candidates = []
    for item in value.split(","):
        parts = item.strip().split()
        if parts:
            descriptor = parts[1] if len(parts) > 1 else "1x"
            candidates.append((parts[0], descriptor))
    if not candidates:
        return ""
    def rank(item):
        match = re.match(r"(\\d+(?:\\.\\d+)?)(w|x)", item[1])
        return float(match.group(1)) if match else 1
    return max(candidates, key=rank)[0]

def is_noise_element(tag):
    marker = " ".join([
        str(tag.get("id", "")),
        " ".join(tag.get("class", [])) if isinstance(tag.get("class", []), list) else str(tag.get("class", "")),
        str(tag.get("aria-label", "")),
        str(tag.get("role", "")),
    ]).lower()
    return bool(re.search(
        r"related|recommend|popular|trending|breadcrumb|sidebar|advert|ads|newsletter|comment|social|share|tag-list|topic-list|terkait|terpopuler|baca-juga|artikel-lain|most-read|more-stories",
        marker
    ))

def is_noise_heading(text):
    t = clean_text(text).lower()
    if not t:
        return True
    return bool(re.search(
        r"^(topik terkait|artikel terkait|baca juga|berita terkait|berita lainnya|mom'?s life|haibunda|terpopuler|paling banyak dibaca|foto|infografis|advertorial)$",
        t
    ))

def metadata_content(soup, selector):
    node = soup.select_one(selector)
    return clean_text(node.get("content", "")) if node else ""

def extract_images(soup, article_root, page_url):
    found = []
    seen = set()

    def add(raw_url, kind="inline", node=None, caption="", alt="", credit=""):
        url = absolute_image_url(raw_url, page_url)
        if not url or url in seen:
            return
        low = url.lower()
        if any(x in low for x in ("logo", "avatar", "icon", "sprite", "pixel", "tracking")):
            return
        seen.add(url)
        found.append({
            "image_id": f"IMG-{len(found)+1:03d}",
            "image_url": url,
            "image_type": kind,
            "caption": clean_text(caption),
            "alt_text": clean_text(alt),
            "credit": clean_text(credit),
            "source_article": page_url,
            "position": len(found)+1,
            "extraction_status": "URL ditemukan; tampilan perlu diverifikasi"
        })

    # Featured image from common metadata.
    featured = first_value([
        metadata_content(soup, 'meta[property="og:image"]'),
        metadata_content(soup, 'meta[name="twitter:image"]'),
        metadata_content(soup, 'meta[property="twitter:image"]')
    ])
    if not featured:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                obj = json.loads(script.string or script.get_text())
                stack = obj if isinstance(obj, list) else [obj]
                for item in stack:
                    if isinstance(item, dict) and item.get("@type") in ("NewsArticle", "Article", "BlogPosting"):
                        img = item.get("image")
                        if isinstance(img, str):
                            featured = img
                        elif isinstance(img, list) and img:
                            featured = img[0] if isinstance(img[0], str) else img[0].get("url", "")
                        elif isinstance(img, dict):
                            featured = img.get("url", "")
                        if featured:
                            break
            except Exception:
                pass
            if featured:
                break
    if featured:
        add(featured, "featured")

    if article_root:
        for node in article_root.find_all(["img", "picture"]):
            img = node if node.name == "img" else node.find("img")
            sources = node.find_all("source") if node.name == "picture" else []
            raw = ""
            if img:
                raw = first_value([
                    img.get("src"),
                    img.get("data-src"),
                    img.get("data-original"),
                    img.get("data-lazy-src"),
                    best_srcset(img.get("srcset"))
                ])
            if not raw:
                for source in sources:
                    raw = first_value([best_srcset(source.get("srcset")), source.get("src")])
                    if raw:
                        break
            if not raw:
                continue
            figure = node.find_parent("figure") or (img.find_parent("figure") if img else None)
            caption = figure.find("figcaption").get_text(" ", strip=True) if figure and figure.find("figcaption") else ""
            alt = img.get("alt", "") if img else ""
            credit_node = figure.select_one('[class*="credit"], [class*="author"], [class*="copyright"]') if figure else None
            credit = credit_node.get_text(" ", strip=True) if credit_node else ""
            add(raw, "inline", node, caption, alt, credit)

    # Include metadata image even if not present in the article body.
    return found

def fetch_article(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError("URL tidak mengarah ke halaman HTML.")
    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    title = first_value([
        metadata_content(soup, 'meta[property="og:title"]'),
        soup.title.get_text(" ", strip=True) if soup.title else ""
    ])
    desc = first_value([
        metadata_content(soup, 'meta[name="description"]'),
        metadata_content(soup, 'meta[property="og:description"]')
    ])
    canonical_node = soup.select_one('link[rel="canonical"]')
    canonical = urljoin(url, canonical_node.get("href", "")) if canonical_node else ""

    selectors = ['[itemprop="articleBody"]', "article", "main", '[class*="article-content"]',
                 '[class*="article__content"]', '[class*="detail-content"]', '[class*="content-article"]']
    candidates = []
    for selector in selectors:
        try:
            candidates.extend(soup.select(selector))
        except Exception:
            pass
    candidates = list(dict.fromkeys(candidates))
    root = max(candidates, key=lambda x: len(x.find_all("p")) * 100 + len(x.get_text(" ", strip=True)), default=None)
    article_root = deepcopy(root) if root else None

    images = extract_images(soup, article_root, url)
    headings, links = [], []
    body = ""
    if article_root:
        for node in list(article_root.find_all(True)):
            if is_noise_element(node):
                node.decompose()
        for tag in article_root.find_all(re.compile(r"^h[1-6]$")):
            txt = clean_text(tag.get_text(" ", strip=True))
            if txt and not is_noise_heading(txt) and len(txt) < 180:
                headings.append((tag.name.upper(), txt))
        host = urlparse(url).netloc.lower()
        for a in article_root.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if urlparse(href).scheme in ("http", "https"):
                links.append((clean_text(a.get_text(" ", strip=True)), href, urlparse(href).netloc.lower() == host))
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
        body = "\\n\\n".join(blocks)

    if len(body) < 250:
        extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                                        favor_recall=True, deduplicate=True)
        if extracted and len(extracted.strip()) > len(body):
            body = clean_text(extracted)
    return {
        "title": title, "description": desc, "canonical": canonical, "headings": headings,
        "body": body, "images": images, "links": links, "status": response.status_code
    }

def keywords(text, n=20):
    words = re.findall(r"(?u)\\b[\\w-]{3,}\\b", text.lower())
    words = [w for w in words if w not in STOPWORDS and not w.isdigit()]
    return Counter(words).most_common(n)

def intent_guess(title, body):
    t = (title + " " + body[:1800]).lower()
    if re.search(r"\\b(harga|review|terbaik|rekomendasi|vs|perbandingan|beli|produk)\\b", t):
        return "Komersial / investigasi komersial"
    if re.search(r"\\b(cara|tips|tutorial|panduan|langkah|apa itu|mengapa|bagaimana|penelitian)\\b", t):
        return "Informasional"
    if re.search(r"\\b(login|masuk|daftar|website resmi|situs resmi)\\b", t):
        return "Navigasional"
    return "Belum dapat dipastikan (kemungkinan informasional)"

def score_article(data):
    words = re.findall(r"(?u)\\b[\\w-]+\\b", data["body"])
    headings = data["headings"]
    checks = [
        ("Judul halaman tersedia", bool(data["title"]), "Tambahkan title yang spesifik."),
        ("Meta description tersedia", bool(data["description"]), "Tulis meta description yang unik."),
        ("H1 tersedia", any(x[0] == "H1" for x in headings), "Tambahkan satu H1 yang menggambarkan topik utama."),
        ("Konten cukup panjang (≥600 kata)", len(words) >= 600, "Perluas pembahasan jika topik membutuhkan kedalaman."),
        ("Struktur subjudul tersedia", any(x[0] in ("H2", "H3") for x in headings), "Gunakan H2/H3 yang deskriptif."),
        ("Gambar memiliki alt text", bool(data["images"]) and all(x["alt_text"] for x in data["images"]), "Tambahkan alt text deskriptif pada gambar informatif."),
        ("Tautan internal tersedia", any(x[2] for x in data["links"]), "Tambahkan tautan internal relevan.")
    ]
    return round(sum(ok for _, ok, _ in checks) / len(checks) * 100), checks

def make_rewriter_prompt(data, analysis):
    image_lines = []
    for img in data["images"]:
        image_lines.append(
            f"- {img['image_id']} | tipe: {img['image_type']} | URL: {img['image_url']} | "
            f"alt: {img['alt_text'] or 'tidak tersedia'} | caption: {img['caption'] or 'tidak tersedia'} | "
            f"kredit: {img['credit'] or 'tidak tersedia'}"
        )
    images = "\\n".join(image_lines) if image_lines else "Tidak ada gambar yang berhasil diekstrak."
    return f"""Buat artikel baru yang orisinal dan SEO-friendly berdasarkan data berikut. Jangan sekadar memparafrasekan kalimat sumber. Pertahankan fakta yang dapat diverifikasi, jangan mengarang data, dan jelaskan keterbatasan sumber bila relevan.

JUDUL SUMBER: {data['title']}
URL SUMBER: {analysis['url']}
SEARCH INTENT: {analysis['intent']}
KEYWORD UTAMA (indikasi): {analysis['keywords'][0][0] if analysis['keywords'] else 'Tentukan dari topik'}
KATA KUNCI TERKAIT: {', '.join(k for k, _ in analysis['keywords'][:15])}
REKOMENDASI SEO:
{chr(10).join('- ' + x for x in analysis['recommendations']) or '- Pertahankan akurasi dan tingkatkan nilai praktis.'}

TEKS ARTIKEL SUMBER:
{data['body']}

DATA GAMBAR SUMBER:
{images}

INSTRUKSI GAMBAR:
1. Tampilkan daftar gambar sumber dan tentukan gambar utama serta posisi gambar pendukung yang relevan.
2. Gunakan URL gambar asli hanya jika dapat diakses dan pengguna memiliki hak/izin untuk menggunakannya.
3. Jangan mengklaim gambar tersedia jika URL gagal dimuat. Jangan mengganti gambar sumber dengan gambar ilustrasi lalu menyebutnya gambar asli.
4. Pertahankan kredit dan atribusi; buat alt text dan caption yang akurat untuk konteks artikel baru.
5. Sisipkan placeholder gambar pada posisi yang disarankan, misalnya [GAMBAR IMG-001 — setelah paragraf pembuka].
6. Hasilkan judul SEO, meta description, keyword, artikel H1-H3, FAQ, kesimpulan, saran internal link, dan catatan verifikasi fakta.
"""

st.title("🔎 Article Research & SEO Analyzer")
st.caption("Riset artikel, pemeriksaan SEO, ekstraksi gambar, dan persiapan Rewriter.")
st.info("Aplikasi gratis tanpa API berbayar. Ekstraksi bergantung pada akses publik situs. Skor dan keyword merupakan estimasi heuristik, bukan data resmi Google.")

url = st.text_input("URL artikel", placeholder="https://contoh.com/judul-artikel")
analyze = st.button("Full Analysis", type="primary", use_container_width=True)

if analyze:
    if not url.strip():
        st.error("Masukkan URL artikel terlebih dahulu.")
    else:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            st.error("Masukkan URL lengkap yang diawali http:// atau https://.")
        else:
            with st.spinner("Mengambil artikel dan gambar..."):
                try:
                    data = fetch_article(url.strip())
                    if len(data["body"]) < 120:
                        st.warning("Teks artikel yang berhasil diekstrak sangat sedikit. Situs mungkin memakai JavaScript, paywall, atau proteksi bot.")
                    st.session_state["analysis_data"] = data
                    st.session_state["analysis_url"] = url.strip()
                except requests.exceptions.Timeout:
                    st.error("Waktu akses habis. Coba lagi.")
                except requests.exceptions.RequestException as exc:
                    st.error(f"Tidak dapat mengambil halaman: {exc}")
                except Exception as exc:
                    st.error(f"Analisis gagal: {exc}")

if "analysis_data" in st.session_state:
    d = st.session_state["analysis_data"]
    body = d["body"]
    word_count = len(re.findall(r"(?u)\\b[\\w-]+\\b", body))
    kw = keywords(body)
    score, checks = score_article(d)
    intent = intent_guess(d["title"], body)
    recommendations = [fix for _, ok, fix in checks if not ok]
    analysis = {"url": st.session_state["analysis_url"], "intent": intent, "keywords": kw, "recommendations": recommendations}

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Skor pemeriksaan SEO", f"{score}/100")
    c2.metric("Jumlah kata", f"{word_count:,}")
    c3.metric("Subjudul", sum(1 for h, _ in d["headings"] if h in ("H2", "H3")))
    c4.metric("Gambar ditemukan", len(d["images"]))

    tab1, tab2, tab3, tab4 = st.tabs(["Full Analysis", "Gambar Artikel", "Rewriter", "Ekspor"])
    with tab1:
        st.subheader("Identitas artikel")
        st.write("**URL:**", analysis["url"])
        st.write("**Judul:**", d["title"] or "Tidak terdeteksi")
        st.write("**Meta description:**", d["description"] or "Tidak terdeteksi")
        st.write("**Canonical:**", d["canonical"] or "Tidak terdeteksi")
        st.subheader("Inti artikel")
        st.write(body[:1800] + ("..." if len(body) > 1800 else ""))
        if len(body) > 1800:
            with st.expander("Lihat seluruh teks hasil ekstraksi"):
                st.text(body)
        st.subheader("Search intent")
        st.write(intent)
        st.subheader("Kata kunci terdeteksi")
        if kw:
            st.dataframe([{"Kata": k, "Frekuensi": v} for k, v in kw], use_container_width=True, hide_index=True)
        st.caption("Frekuensi kata bukan volume pencarian atau riset keyword kompetitif.")
        st.subheader("Struktur heading")
        if d["headings"]:
            for level, heading in d["headings"]:
                st.write(f"{'　' * (int(level[1])-1)}**{level}** — {heading}")
        else:
            st.write("Tidak ditemukan heading H1–H6.")
        st.subheader("Pemeriksaan SEO on-page")
        for label, ok, fix in checks:
            st.write(("✅ " if ok else "⚠️ ") + label + ("" if ok else " — " + fix))
        st.subheader("Rekomendasi dan prioritas")
        for item in recommendations or ["Pemeriksaan dasar terpenuhi; lanjutkan evaluasi akurasi, orisinalitas, sumber, dan search intent."]:
            st.write("- " + item)
        st.write(f"**Tautan internal:** {sum(1 for x in d['links'] if x[2])} | **Tautan eksternal:** {sum(1 for x in d['links'] if not x[2])}")

    with tab2:
        st.subheader("Gambar yang ditemukan pada artikel")
        st.caption("Gambar ditampilkan dari URL sumber. Sebagian situs memblokir hotlink atau akses otomatis; gambar yang gagal dimuat akan ditandai.")
        if not d["images"]:
            st.warning("Tidak ada gambar yang berhasil diekstrak dari metadata atau kontainer artikel.")
        for img in d["images"]:
            with st.container(border=True):
                st.write(f"**{img['image_id']} — {img['image_type']} — posisi {img['position']}**")
                try:
                    st.image(img["image_url"], use_container_width=True)
                    img["extraction_status"] = "Berhasil dimuat"
                    st.success(img["extraction_status"])
                except Exception:
                    img["extraction_status"] = "URL ditemukan, tetapi gambar gagal dimuat (mungkin hotlink protection atau URL kedaluwarsa)."
                    st.warning(img["extraction_status"])
                st.write("**URL:**", img["image_url"])
                st.write("**Alt text:**", img["alt_text"] or "Tidak tersedia")
                st.write("**Caption:**", img["caption"] or "Tidak tersedia")
                st.write("**Kredit:**", img["credit"] or "Tidak terdeteksi")
        st.info("Gambar sumber tidak otomatis bebas digunakan ulang. Pastikan izin/lisensi dan atribusi sebelum menerbitkan artikel baru.")

    with tab3:
        st.subheader("Rewriter")
        st.write("Rewriter menyusun brief lengkap dari hasil Full Analysis dan data gambar. Brief dapat disalin ke asisten AI untuk menghasilkan naskah; aplikasi ini tidak mengklaim menghasilkan teks AI secara mandiri tanpa layanan model.")
        if st.button("Susun brief Rewriter", type="primary"):
            st.session_state["rewriter_prompt"] = make_rewriter_prompt(d, analysis)
        if st.session_state.get("rewriter_prompt"):
            st.text_area("Brief Rewriter (termasuk daftar gambar sumber)", st.session_state["rewriter_prompt"], height=420)
            st.download_button("Unduh brief Rewriter", st.session_state["rewriter_prompt"], file_name="rewriter_brief.txt", mime="text/plain")
        st.subheader("Panduan gambar untuk artikel baru")
        st.write("Gunakan gambar utama sebagai featured image bila relevan dan berizin. Tempatkan gambar pendukung setelah bagian yang dibahasnya. Jangan mengarang URL, kredit, atau status izin.")

    with tab4:
        report = f"""ARTICLE RESEARCH & SEO ANALYSIS
URL: {analysis['url']}
TITLE: {d['title']}
META DESCRIPTION: {d['description']}
SEO CHECK SCORE: {score}/100
WORD COUNT: {word_count}
SEARCH INTENT: {intent}

KEYWORDS:
""" + "\\n".join(f"- {k}: {v}" for k, v in kw) + "\\n\\nHEADINGS:\\n" + "\\n".join(f"- {a}: {b}" for a, b in d["headings"]) + "\\n\\nIMAGE INVENTORY:\\n" + "\\n".join(f"- {x['image_id']} | {x['image_type']} | {x['image_url']} | alt={x['alt_text']} | caption={x['caption']} | credit={x['credit']}" for x in d["images"]) + "\\n\\nRECOMMENDATIONS:\\n" + "\\n".join("- " + x for x in recommendations) + "\\n\\nARTICLE TEXT:\\n" + body
        st.download_button("Unduh laporan Full Analysis", report, file_name="laporan_article_seo.txt", mime="text/plain")
        if d["images"]:
            st.download_button("Unduh inventaris gambar (JSON)", json.dumps(d["images"], ensure_ascii=False, indent=2), file_name="inventaris_gambar.json", mime="application/json")

with st.expander("Catatan penggunaan dan batasan"):
    st.markdown("""
    - Tidak membutuhkan API berbayar atau kunci API.
    - Ekstraksi gambar mengambil metadata sosial dan gambar dari kontainer artikel, termasuk lazy loading dan srcset bila tersedia.
    - Situs dapat memblokir scraping, hotlink, JavaScript, atau akses otomatis; hasil gambar/teks mungkin tidak lengkap.
    - Rewriter pada versi ini membuat brief/prompt berdasarkan analisis dan inventaris gambar. Pembuatan naskah AI otomatis memerlukan integrasi model AI terpisah.
    - Gambar artikel pihak ketiga tetap tunduk pada hak cipta dan lisensi. URL yang dapat ditampilkan bukan bukti izin penggunaan ulang.
    - Search intent, frekuensi keyword, dan skor adalah estimasi otomatis; aplikasi tidak mengambil volume keyword, ranking Google, backlink, atau data Search Console.
    """)
