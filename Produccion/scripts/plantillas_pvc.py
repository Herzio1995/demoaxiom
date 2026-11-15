"""
Plantillas 1:1 en hojas carta (o A4) para cortar a mano las bandejas de PVC (o cualquier pieza DXF de una carpeta).

Lee los DXF de cnc/pvc (los genera alucobond_bandejas_ovum1_9.py con mat=pvc) y reparte cada pieza en hojas
verticales a escala 1:1, con 10 mm de solape entre hojas, marcas de registro, centros de agujeros, lineas de doblez
y una barra de 50 mm para comprobar que la impresora no escalo. Sale un HTML y, con Edge, un PDF.

Uso:  python plantillas_pvc.py [carpeta_dxf] [patron] [carta|a4]   (por defecto ../cnc/pvc, *_PVC2_*.dxf y carta)
IMPRIMIR AL 100 % ("tamano real", sin "ajustar a la pagina") y verificar la barra de 50 mm antes de cortar.
"""
import os, sys, glob, math, subprocess, html

args = [a for a in sys.argv[1:] if a.lower() not in ("carta", "letter", "a4")]
PAPEL = "a4" if any(a.lower() == "a4" for a in sys.argv[1:]) else "carta"
DIR = args[0] if len(args) > 0 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cnc", "pvc")
PAT = args[1] if len(args) > 1 else "*_PVC2_*.dxf"
INOX = "INOX" in PAT.upper()          # bandejas de inox 0.6 (bandejas_inox_ovum2_4.py)
MATL = "INOX" if INOX else "PVC"
PW, PH = (210.0, 297.0) if PAPEL == "a4" else (215.9, 279.4)     # vertical (mm)
CSS_PAGE = "A4" if PAPEL == "a4" else "letter"
SUF = "A4" if PAPEL == "a4" else "Carta"
M = 9.0                        # margen sin imprimir
SOL = 10.0                     # solape entre hojas
UW, UH = PW - 2 * M, PH - 2 * M - 8.0      # zona util (abajo quedan 8 mm para la barra y el rotulo)

def read_dxf(path):
    L = [l.rstrip("\r\n") for l in open(path, encoding="utf-8", errors="replace")]
    pairs = [(L[i].strip(), L[i + 1]) for i in range(0, len(L) - 1, 2)]
    polys, lines, texts = [], [], []; i = 0; ent = False
    while i < len(pairs):
        c, v = pairs[i]
        if c == "2" and v == "ENTITIES": ent = True
        if ent and c == "0" and v == "POLYLINE":
            lay = None; pts = []; i += 1
            while not (pairs[i][0] == "0" and pairs[i][1] == "VERTEX"):
                if pairs[i][0] == "8": lay = pairs[i][1]
                i += 1
            while pairs[i][1] != "SEQEND":
                if pairs[i][0] == "0" and pairs[i][1] == "VERTEX":
                    x = y = None; i += 1
                    while pairs[i][0] != "0":
                        if pairs[i][0] == "10": x = float(pairs[i][1])
                        if pairs[i][0] == "20": y = float(pairs[i][1])
                        i += 1
                    pts.append((x, y)); continue
                i += 1
            polys.append((lay, pts)); continue
        if ent and c == "0" and v == "LINE":
            d = {}; i += 1
            while pairs[i][0] != "0": d[pairs[i][0]] = pairs[i][1]; i += 1
            lines.append((d["8"], (float(d["10"]), float(d["20"])), (float(d["11"]), float(d["21"])))); continue
        if ent and c == "0" and v == "TEXT":
            d = {}; i += 1
            while pairs[i][0] != "0": d[pairs[i][0]] = pairs[i][1]; i += 1
            texts.append((d["8"], (float(d["10"]), float(d["20"])), float(d["40"]), d["1"])); continue
        i += 1
    return polys, lines, texts

def es_agujero(pts):
    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    r = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
    return (cx, cy, r) if r < 4.0 and min(math.hypot(p[0] - cx, p[1] - cy) for p in pts) > 0.7 * r else None

def hojas(w, h):
    nx = 1 if w <= UW else math.ceil((w - SOL) / (UW - SOL)); ny = 1 if h <= UH else math.ceil((h - SOL) / (UH - SOL))
    return nx, ny

paginas = []; indice = []
archivos = sorted(f for f in glob.glob(os.path.join(DIR, PAT)) if "_CORTE" not in os.path.basename(f))
for f in archivos:
    polys, lines, texts = read_dxf(f)
    nombre = os.path.basename(f)[:-4].replace("_PVC2_", " ").replace("_INOX06_", " ")
    pts = [p for _, ps in polys for p in ps] + [q for _, a, b in lines for q in (a, b)]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    y1 = max([y1] + [t[1][1] + t[2] for t in texts if x0 - 5 <= t[1][0] <= x1 + 5])
    w, h = x1 - x0, y1 - y0
    rot = hojas(h, w)[0] * hojas(h, w)[1] < hojas(w, h)[0] * hojas(w, h)[1]     # acostar la pieza si ocupa menos hojas
    def T(p, x0=x0, y0=y0, w=w, rot=rot):
        x, y = p[0] - x0, p[1] - y0
        return (y, w - x) if rot else (x, y)
    W_, H_ = (h, w) if rot else (w, h)
    nx, ny = hojas(W_, H_)
    stx = (W_ - UW) / (nx - 1) if nx > 1 else 0.0; sty = (H_ - UH) / (ny - 1) if ny > 1 else 0.0
    p0 = len(paginas) + 2
    for j in range(ny):
        for i in range(nx):
            ox, oy = i * stx, (ny - 1 - j) * sty            # fila 1 = arriba de la pieza
            def P(p):
                x, y = T(p); return (M + (x - ox), M + UH - (y - oy))
            s = []
            s.append(f'<rect x="{M}" y="{M}" width="{UW}" height="{UH}" fill="none" stroke="#bbb" stroke-width="0.2" stroke-dasharray="1,1"/>')
            s.append(f'<g clip-path="url(#c)">')
            for lay, ps in polys:
                ag = es_agujero(ps) if lay == "CORTE_INTERIOR" else None
                if ag:
                    cx, cy = P((ag[0], ag[1]))
                    s.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ag[2]:.2f}" fill="none" stroke="#d00" stroke-width="0.25"/>')
                    s.append(f'<path d="M{cx-2.5:.2f},{cy:.2f}h5M{cx:.2f},{cy-2.5:.2f}v5" stroke="#d00" stroke-width="0.15"/>')
                    continue
                d = "M" + "L".join("%.2f,%.2f" % P(q) for q in ps) + "Z"
                col, sw = ("#000", 0.35) if lay == "CORTE_EXTERIOR" else ("#d00", 0.3)
                s.append(f'<path d="{d}" fill="{"#f4f6f8" if lay == "CORTE_EXTERIOR" else "#fff"}" stroke="{col}" stroke-width="{sw}"/>')
            for lay, a, b in lines:
                if lay in ("DOBLEZ", "RANURA_V"):
                    (ax, ay), (bx, by) = P(a), P(b)
                    s.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" y2="{by:.2f}" stroke="#1565c0" stroke-width="0.35" stroke-dasharray="3,1.5"/>')
            for lay, q, hh, txt in texts:
                if txt.startswith("Referencia"): continue
                x, y = P(q)
                s.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{hh:.1f}" font-family="Arial" fill="#2e7d32">{html.escape(txt)}</text>')
            s.append('</g>')
            # marcas de registro en el solape (para alinear las hojas)
            for k_ in range(1, 4):
                if i > 0:
                    yy = M + UH * k_ / 4; xx = M + SOL / 2
                    s.append(f'<path d="M{xx-3},{yy}h6M{xx},{yy-3}v6" stroke="#000" stroke-width="0.2"/><circle cx="{xx}" cy="{yy}" r="1.5" fill="none" stroke="#000" stroke-width="0.2"/>')
                if i < nx - 1:
                    yy = M + UH * k_ / 4; xx = M + UW - SOL / 2
                    s.append(f'<path d="M{xx-3},{yy}h6M{xx},{yy-3}v6" stroke="#000" stroke-width="0.2"/><circle cx="{xx}" cy="{yy}" r="1.5" fill="none" stroke="#000" stroke-width="0.2"/>')
                if j > 0:
                    xx = M + UW * k_ / 4; yy = M + SOL / 2
                    s.append(f'<path d="M{xx-3},{yy}h6M{xx},{yy-3}v6" stroke="#000" stroke-width="0.2"/><circle cx="{xx}" cy="{yy}" r="1.5" fill="none" stroke="#000" stroke-width="0.2"/>')
                if j < ny - 1:
                    xx = M + UW * k_ / 4; yy = M + UH - SOL / 2
                    s.append(f'<path d="M{xx-3},{yy}h6M{xx},{yy-3}v6" stroke="#000" stroke-width="0.2"/><circle cx="{xx}" cy="{yy}" r="1.5" fill="none" stroke="#000" stroke-width="0.2"/>')
            if i > 0: s.append(f'<line x1="{M+SOL}" y1="{M}" x2="{M+SOL}" y2="{M+UH}" stroke="#999" stroke-width="0.2" stroke-dasharray="0.6,1.2"/>')
            if j > 0: s.append(f'<line x1="{M}" y1="{M+SOL}" x2="{M+UW}" y2="{M+SOL}" stroke="#999" stroke-width="0.2" stroke-dasharray="0.6,1.2"/>')
            yb = PH - M - 3.0
            s.append(f'<path d="M{M},{yb}h50M{M},{yb-1.5}v3M{M+50},{yb-1.5}v3" stroke="#000" stroke-width="0.3"/>')
            s.append(f'<text x="{M+53}" y="{yb+1}" font-size="2.6" font-family="Arial">50 mm (medir antes de cortar)</text>')
            rot_t = " (acostada)" if rot else ""
            s.append(f'<text x="{PW-M}" y="{yb+1}" font-size="3" font-family="Arial" text-anchor="end">{html.escape(nombre)}{rot_t} - hoja fila {j+1}/{ny}, col {i+1}/{nx}</text>')
            paginas.append("".join(s))
    indice.append((nombre, nx * ny, p0, len(paginas) + 1, round(w), round(h)))

idx = [f'<text x="15" y="22" font-size="7" font-family="Arial" font-weight="bold">Plantillas 1:1 - bandejas {'inox 0.6 mm' if INOX else 'PVC 2 mm'} - hoja {SUF.lower()}</text>',
       f'<text x="15" y="31" font-size="3.4" font-family="Arial">Papel {SUF.upper()} ({PW:g} x {PH:g} mm). Imprimir al 100 % (tamano real, NO ajustar a la pagina). Comprobar la barra de 50 mm.</text>',
       '<text x="15" y="36" font-size="3.4" font-family="Arial">Unir hojas solapando 10 mm sobre las marcas de registro. Negro = corte exterior; rojo = agujeros/ranuras;</text>',
       ('<text x="15" y="41" font-size="3.4" font-family="Arial">azul punteado = DOBLAR en frio con plegadora o angulos (no cortar). Cara impresa = cara de los huevos.</text>'
        '<text x="15" y="46" font-size="3.4" font-family="Arial">Paredes hacia arriba al angulo indicado. Pliegues del piso: valle = hacia arriba, MONTE = hacia abajo.</text>'
        '<text x="15" y="51" font-size="3.4" font-family="Arial">Agujeros D3.2 (remache 3 mm). Las lineas negras que llegan hasta un vertice son cortes rectos.</text>')
       if INOX else
       '<text x="15" y="41" font-size="3.4" font-family="Arial">azul punteado = DOBLAR con calor (no cortar), con el angulo y la cara concava indicados.</text>']
yy = 61 if INOX else 52
for nm, n, a, b, w, h in indice:
    idx.append(f'<text x="15" y="{yy}" font-size="3.2" font-family="Arial">{html.escape(nm)}  -  {w} x {h} mm  -  {n} hoja(s): pag. {a}{"" if a == b else "-" + str(b)}</text>'); yy += 5.2
paginas.insert(0, "".join(idx))
doc = [f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{CSS_PAGE};margin:0}}body{{margin:0}}'
       f'svg{{display:block;width:{PW}mm;height:{PH}mm;page-break-after:always}}</style></head><body>']
for pg in paginas:
    doc.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PW} {PH}" width="{PW}mm" height="{PH}mm">'
               f'<defs><clipPath id="c"><rect x="{M}" y="{M}" width="{UW}" height="{UH}"/></clipPath></defs>{pg}</svg>')
doc.append("</body></html>")
out_html = os.path.join(DIR, f"Plantillas_{MATL}_{SUF}.html"); open(out_html, "w", encoding="utf-8").write("".join(doc))
out_pdf = os.path.join(DIR, f"Plantillas_{MATL}_{SUF}.pdf")
edge = next((e for e in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if os.path.exists(e)), None)
if edge:
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={os.path.abspath(out_pdf)}",
                    "file:///" + os.path.abspath(out_html).replace("\\", "/")], timeout=180)
print("piezas:", len(indice), " paginas:", len(paginas))
for nm, n, a, b, w, h in indice: print(f"  {nm:<28} {w:>5} x {h:<5} mm  {n:>2} hojas")
print("->", out_pdf if edge and os.path.exists(out_pdf) else out_html)
