"""
Ovum1_9 / Ovum2_0: las 5 bandejas. Material con mat= (por defecto pvc):
  mat=pvc : PROTOTIPO en lamina de PVC de 2 mm, cortada a mano con plantillas 1:1 (plantillas_pvc.py), pliegues
            doblados con calor, escuadras impresas en PETG y tornillos M3 + tuerca (en vez de remaches).
  mat=acm : alucobond (ACM) de 4 mm para CNC, con ranurado en V y plegado, escuadras de aluminio y remaches.
  BandejaCentral, BandejaLTop / BandejaRTop (superiores laterales), BandejaLDown / BandejaRDown (inferiores).
Reemplaza a alucobond_bandeja_central_ovum1_9.py (la central se rehace aqui porque comparte paredes).

Reglas
- La superficie por donde ruedan los huevos (la de cada malla) no cambia: el material crece hacia afuera
  (bajo el piso y por fuera de las paredes).
- Piso: 1 pieza por bandeja, ranuras V por la cara inferior (B); el desarrollo es la cara de los huevos.
- Paredes: cadenas de caras verticales, cortadas en piezas donde cambia el sentido del pliegue.
- Pared propia: termina al ras de la cara inferior del piso; las pestanas del piso entran en muescas abiertas
  y una escuadra de aluminio por fuera abraza la arista (ala bajo el piso + ala por fuera de la pared).
- Pared compartida (central/laterales superiores, LDown/RDown): una sola pared; el piso vecino llega hasta su
  cara exterior. Baja M_SLOT bajo el piso mas bajo y todas las pestanas entran en ranuras cerradas (sin escuadra).
- Pared en rendija (pared propia con otra pared a menos de GAP_WALL por fuera): sin lugar para escuadras;
  ranuras cerradas. Entre una lateral superior y la central: remaches pasantes con separador.
- Transicion rasante de compartida a propia: cuna impresa en PETG que tapa el escalon (= espesor del panel).
Uso:  blender --background Ovum2_0.blend --python alucobond_bandejas_ovum1_9.py -- [mat=pvc|acm] [t=2] [out <dir>] [save]
"""
import bpy, bmesh, json, sys, math, os
from mathutils import Vector, Matrix
from mathutils.geometry import tessellate_polygon
from mathutils.bvhtree import BVHTree
from collections import Counter

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MAT = next((a.split("=")[1] for a in argv if a.startswith("mat=")), "pvc").lower()
PVC = MAT == "pvc"
OUT = argv[argv.index("out") + 1] if "out" in argv else os.path.join(os.path.dirname(bpy.data.filepath), "cnc", "pvc" if PVC else "alucobond")
os.makedirs(OUT, exist_ok=True)
STL_OUT = os.path.join(os.path.dirname(bpy.data.filepath), "stl", "bandejas_pvc")
PFX = "PVC_" if PVC else "ACM_"              # prefijo de los objetos de las bandejas
CPFX = "PVC_" if PVC else "Alucobond_"       # prefijo de las colecciones
MATNOM = "PVC" if PVC else "ACM"
LIN = "DOBLEZ" if PVC else "RANURA_V"        # capa de las lineas de pliegue

# ------------------------------------------------------------------ parametros (mm)
T = float(next((a.split("=")[1] for a in argv if a.startswith("t=")), 2.0 if PVC else 4.0))   # PVC 2 mm / ACM 4 mm
TAG = f"{MATNOM}{T:g}"
C_PISO = 0.15    # holgura borde del piso - cara de la pared
C_SLOT = 0.15    # holgura pestana - ranura (por lado)
W_TAB = 15.0     # ancho de pestana
TAB_PASO = 75.0  # una pestana cada ~75 mm
TAB_MIN_SEG = 35.0
R_TOOL = 1.6     # radio de la fresa (1/8")
M_SLOT = 3.5     # paredes compartidas / en rendija: bajan 3.5 mm bajo el piso mas bajo (ranuras cerradas)
R_HOLE = 1.7 if PVC else 2.05    # PVC: D3.4 para tornillo M3 / ACM: D4.1 para remache ciego D4
CLIP_H = 20.0    # escuadra: ala bajo el piso, desde la cara exterior de la pared
CLIP_V = 18.0    # escuadra: ala exterior, desde la cara inferior del piso
CLIP_T = 2.5 if PVC else 2.0      # escuadra: PETG impreso 2.5 mm / aluminio 2 mm
RIV_PISO = 8.0   # remache del piso a 8 mm de la cara interior de la pared
RIV_PARED = 6.0  # remache de la pared a 6 mm sobre el piso (cabeza por dentro)
RESTO = 0.8      # material en el fondo de la ranura V
GAP_SHARED = max(2 * T + 0.3, 8.3)   # se comparten si estan mas cerca que esto (min. 8.3: misma topologia que con 4 mm)
GAP_WALL = 12.0            # rendija entre paredes en la que no cabe una escuadra
SHALLOW = 30.0             # transicion compartida -> propia con angulo menor: cuna PETG
MIN_RUN = 8.0              # tramo compartido minimo (mas corto: queda pared propia)
FLAT_TURN = 3.0            # pliegues de pared menores a esto no definen el sentido de la pieza
EGG_R = 21.0               # radio del huevo acostado (para holguras de cabezas de remache)

TRAYS = ["BandejaCentral", "BandejaLTop", "BandejaRTop", "BandejaLDown", "BandejaRDown"]
PAIRS = [("BandejaLTop", "BandejaCentral"), ("BandejaRTop", "BandejaCentral"), ("BandejaRDown", "BandejaLDown"),
         ("BandejaLDown", "BandejaLTop"), ("BandejaRDown", "BandejaRTop")]   # (bandeja cuyo piso llega, duena de la pared)
def owners_of(n): return [o for a, o in PAIRS if a == n]
def partners_of(o): return [a for a, b in PAIRS if b == o]
def paired(a, b): return (a, b) in PAIRS or (b, a) in PAIRS
IGNORAR = ("ACM_", "PVC_", "Bandeja", "Huevo", "PETG_Cuna", "PETG_Escuadras", "PETG_Separador")
CENTRAL_NAMES = {22: "Pared_U", 12: "Embudo_Izq", 13: "Embudo_Der"}   # vertice -> nombre (como antes)
CENTRAR = {"BandejaLDown"}   # pared compartida centrada entre las dos bandejas (si cabe entre sus caras)

O = bpy.data.objects
rep = {"avisos": []}
def aviso(s): rep["avisos"].append(s)

# ------------------------------------------------------------------ geometria basica
def v2(p): return Vector((p.x, p.y))
def norm2(v): return v / v.length
def perp(v): return Vector((-v.y, v.x))
def cross2(a, b): return a.x * b.y - a.y * b.x
def line_x(p1, d1, p2, d2):
    den = cross2(d1, d2)
    if abs(den) < 1e-6: return None
    return p1 + d1 * (cross2(p2 - p1, d2) / den)
def inside2(pt, poly):
    c = False; n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a.y > pt.y) != (b.y > pt.y) and pt.x < (b.x - a.x) * (pt.y - a.y) / (b.y - a.y) + a.x: c = not c
    return c
def seg_dist(p, a, b):
    L2 = (b - a).length_squared
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (p - a).dot(b - a) / L2))
    return (p - (a + (b - a) * t)).length, t
def poly_dist(p, poly):
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)])[0] for i in range(len(poly)))
def area2(poly):
    return 0.5 * sum(poly[i].x * poly[(i + 1) % len(poly)].y - poly[(i + 1) % len(poly)].x * poly[i].y for i in range(len(poly)))
def ccw(poly): return poly if area2(poly) > 0 else list(reversed(poly))
def newell(pts):
    n = Vector((0.0, 0.0, 0.0))
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z); n.y += (a.z - b.z) * (a.x + b.x); n.z += (a.x - b.x) * (a.y + b.y)
    return n.normalized()
def plane_dev(pts):
    n = newell(pts); c = sum(pts, Vector()) / len(pts)
    return max(abs((p - c).dot(n)) for p in pts)
def hull(pts):
    P = sorted({(round(p.x, 3), round(p.y, 3)) for p in pts})
    if len(P) < 3: return [Vector(p) for p in P]
    def cr(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 1e-9: lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 1e-9: up.pop()
        up.append(p)
    return [Vector(p) for p in lo[:-1] + up[:-1]]
def offset_convex(poly, c):
    poly = ccw(poly); n = len(poly); L = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]; d = norm2(b - a); L.append((a + Vector((d.y, -d.x)) * c, d))
    return [line_x(L[i - 1][0], L[i - 1][1], L[i][0], L[i][1]) or L[i][0] for i in range(n)]
def dogbone(poly, hole, r=R_TOOL, min_turn=30.0, seg=8):
    """alivios para la fresa. hole=True: esquinas convexas de un agujero; hole=False: esquinas entrantes"""
    poly = ccw(poly); n = len(poly); out = []
    for i in range(n):
        A, P, B = poly[i - 1], poly[i], poly[(i + 1) % n]
        if (P - A).length < 1e-6 or (B - P).length < 1e-6: out.append(P); continue
        a, b = norm2(P - A), norm2(B - P); cr = a.x * b.y - a.y * b.x
        turn = math.degrees(math.acos(max(-1, min(1, a.dot(b)))))
        if turn < min_turn or (cr > 0) != hole: out.append(P); continue
        o = norm2(b - a); c = P + o * r
        E1 = P + a * (2 * r * a.dot(o)); E2 = P + b * (2 * r * b.dot(o))
        t1 = math.atan2(E1.y - c.y, E1.x - c.x); tp = math.atan2(P.y - c.y, P.x - c.x); t2 = math.atan2(E2.y - c.y, E2.x - c.x)
        def norm_a(x): return (x + 2 * math.pi) % (2 * math.pi)
        span = norm_a(t2 - t1); via = norm_a(tp - t1)
        if via > span: span = span - 2 * math.pi
        out.append(E1)
        for k in range(1, seg):
            tt = t1 + span * k / seg; out.append(c + Vector((math.cos(tt), math.sin(tt))) * r)
        out.append(E2)
    return out
def clip_half(poly, p, d, sgn):
    """conserva la parte con sgn * cross(d, q - p) >= 0"""
    out = []
    for i in range(len(poly)):
        a, b = poly[i - 1], poly[i]
        fa = sgn * cross2(d, a - p); fb = sgn * cross2(d, b - p)
        if fb >= 0:
            if fa < 0: out.append(a + (b - a) * (fa / (fa - fb)))
            out.append(b)
        elif fa >= 0: out.append(a + (b - a) * (fa / (fa - fb)))
    return out
def circ(c, r=R_HOLE, n=24):
    return [c + Vector((math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n))) * r for k in range(n)]
def egg_clear(h):
    """luz entre un huevo acostado contra la pared y la pared, a la altura h sobre el piso"""
    return math.sqrt(EGG_R ** 2 + (EGG_R - h) ** 2) - EGG_R

# ------------------------------------------------------------------ analisis de cada bandeja
class Tray: pass

def tjunc(polys, V):
    allv = {i for p in polys for i in p}; out = []
    for p in polys:
        q = []
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]; q.append(a)
            A, B = V[a], V[b]; L2 = (B - A).length_squared; ins = []
            for i in allv:
                if i in (a, b): continue
                t = (V[i] - A).dot(B - A) / L2
                if 1e-4 < t < 1 - 1e-4 and (A + (B - A) * t - V[i]).length < 0.05: ins.append((t, i))
            q += [i for t, i in sorted(ins)]
        out.append(q)
    return out

def split_planar(p, V, tol=0.6):
    if len(p) <= 3 or plane_dev([V[i] for i in p]) < tol: return [p]
    best = None; n = len(p)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1: continue
            a = p[i:j + 1]; b = p[j:] + p[:i + 1]
            sc = max(plane_dev([V[k] for k in a]), plane_dev([V[k] for k in b]))
            if best is None or sc < best[0]: best = (sc, a, b)
    return split_planar(best[1], V, tol) + split_planar(best[2], V, tol)

def chain_loops(nxt):
    loops = []; seen = set()
    for s in sorted(nxt):
        if s in seen: continue
        lp = [s]; seen.add(s); c = nxt.get(s)
        while c is not None and c != s and c not in seen:
            lp.append(c); seen.add(c); c = nxt.get(c)
        loops.append(lp)
    return loops

def analyze(name):
    ob = O[name]; tr = Tray(); tr.name = name
    V = [(ob.matrix_world @ v.co) * 1000.0 for v in ob.data.vertices]; tr.V = V
    fl = []; wl = []
    for p in ob.data.polygons:
        idx = list(p.vertices); n = newell([V[i] for i in idx])
        if abs(n.z) > 0.3: fl.append(idx if n.z > 0 else idx[::-1])
        elif abs(n.z) < 0.1: wl.append(idx)
        else: aviso(f"{name}: cara {idx} ni piso ni pared (nz={n.z:.2f})")
    fl = tjunc(fl, V)
    fl = [q for p in fl for q in split_planar(p, V)]
    emap = {}
    for pi, p in enumerate(fl):
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]; emap.setdefault(frozenset((a, b)), []).append((pi, a, b))
    pn = [newell([V[i] for i in p]) for p in fl]
    par = list(range(len(fl)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for e, l in emap.items():
        if len(l) == 2 and math.degrees(pn[l[0][0]].angle(pn[l[1][0]])) < 1.0: par[f(l[0][0])] = f(l[1][0])
    groups = {}
    for i in range(len(fl)): groups.setdefault(f(i), []).append(i)
    tr.G = []; gid = {}
    for k, mem in enumerate(groups.values()):
        for i in mem: gid[i] = k
        mset = set(mem); nxt = {}
        for i in mem:
            p = fl[i]
            for q in range(len(p)):
                a, b = p[q], p[(q + 1) % len(p)]
                if not [x for x in emap[frozenset((a, b))] if x[0] != i and x[0] in mset]: nxt[a] = b
        lps = chain_loops(nxt)
        if len(lps) != 1: aviso(f"{name}: grupo de piso con {len(lps)} contornos")
        loop = max(lps, key=len)
        pts = [V[i] for i in loop]; n = newell(pts); c = sum(pts, Vector()) / len(pts)
        tr.G.append(dict(polys=mem, loop=loop, n=n, c=c, d=n.dot(c), plan=[v2(p) for p in pts],
                         area=abs(area2([v2(p) for p in pts]))))
    # pliegues
    fd = {}
    for e, l in emap.items():
        if len(l) == 2 and gid[l[0][0]] != gid[l[1][0]]:
            key = tuple(sorted((gid[l[0][0]], gid[l[1][0]]))); fd.setdefault(key, set()).update(e)
    tr.folds = []
    for (g1, g2), vs in fd.items():
        P = [V[i] for i in vs]; a = P[0]; dd = max(P, key=lambda q: (q - a).length) - a
        P.sort(key=lambda q: (q - a).dot(dd)); A3, B3 = P[0], P[-1]
        n1, n2 = tr.G[g1]["n"], tr.G[g2]["n"]
        e3 = (B3 - A3).normalized(); u2 = n2.cross(e3)
        if u2.dot(tr.G[g2]["c"] - A3) < 0: u2 = -u2
        tr.folds.append(dict(A=A3, B=B3, g1=g1, g2=g2, ang=math.degrees(n1.angle(n2)),
                             tipo="invertido" if u2.dot(n1) > 0 else "normal"))
    # contorno del piso -> registros (un tramo por arista del borde)
    nxt = {}; dirp = {}
    for pi, p in enumerate(fl):
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            if len(emap[frozenset((a, b))]) == 1: nxt[a] = b; dirp[(a, b)] = pi
    lps = chain_loops(nxt)
    if len(lps) != 1: aviso(f"{name}: el piso tiene {len(lps)} contornos")
    loop = max(lps, key=len)
    if area2([v2(V[i]) for i in loop]) < 0: aviso(f"{name}: contorno del piso en sentido horario")
    def wallface(a, b):
        for w in wl:
            if a in w and b in w: return w
        return None
    def top(w, a):
        c = [V[i].z for i in w if i not in (a,) and (v2(V[i]) - v2(V[a])).length < 0.5 and V[i].z > V[a].z + 1]
        return max(c) if c else max(V[i].z for i in w)
    tr.recs = []
    for k in range(len(loop)):
        a, b = loop[k], loop[(k + 1) % len(loop)]; w = wallface(a, b)
        tr.recs.append(dict(A=V[a].copy(), B=V[b].copy(), ta=top(w, a) if w else None, tb=top(w, b) if w else None,
                            g=gid[dirp[(a, b)]], wall=w is not None, kind="own" if w else "free", vi=(a, b), tray=name))
    for r in tr.recs:            # puntos sobre el plano de su cara (los grupos casi coplanares se aproximan con un plano)
        G = tr.G[r["g"]]; n = G["n"]
        for k in ("A", "B"):
            P = r[k]; r[k] = Vector((P.x, P.y, (G["d"] - n.x * P.x - n.y * P.y) / n.z))
    return tr

def geo(r):
    a, b = v2(r["A"]), v2(r["B"]); L = (b - a).length; d = (b - a) / max(L, 1e-9)
    return d, Vector((d.y, -d.x)), L
def ztop(tr, g, X):
    G = tr.G[g]; n = G["n"]; return (G["d"] - n.x * X.x - n.y * X.y) / n.z
def zbot(tr, g, X): return ztop(tr, g, X) - T / tr.G[g]["n"].z
def grp_at(tr, X):
    for k, G in enumerate(tr.G):
        if inside2(X, G["plan"]): return k
    return min(range(len(tr.G)), key=lambda k: poly_dist(X, tr.G[k]["plan"]))
def P3(tr, X, g=None):
    g = grp_at(tr, X) if g is None else g
    return Vector((X.x, X.y, ztop(tr, g, X)))
def split_rec(r, t):
    P = r["A"] + (r["B"] - r["A"]) * t
    tm = None if r["ta"] is None else r["ta"] + (r["tb"] - r["ta"]) * t
    r1 = dict(r); r2 = dict(r); r1["B"] = P.copy(); r1["tb"] = tm; r2["A"] = P.copy(); r2["ta"] = tm
    return r1, r2
def wallframe(tr, g, A3, B3, nw):
    """marco de la union piso/pared: e3 a lo largo, u3 en el plano del piso hacia la pared"""
    nf = tr.G[g]["n"]; e3 = (B3 - A3).normalized(); u3 = e3.cross(nf)
    if u3.dot(nw) < 0: u3 = -u3
    un = u3.dot(nw)
    e_off = max(C_PISO, C_PISO - T * nf.dot(nw)) / un
    lend = (T - max(0.0, -T * nf.dot(nw)) - 0.1) / un
    return dict(e3=e3, nf=nf, nw=nw, u3=u3, un=un, e_off=e_off, lend=lend)

TR = {nm: analyze(nm) for nm in TRAYS if O.get(nm)}
for nm in TR: rep.setdefault("grupos_piso", {})[nm] = len(TR[nm].G)

# ------------------------------------------------------------------ paredes compartidas
def gap_at(P2, r, Ow):
    d, n, L = geo(r); best = None
    for q in Ow.recs:
        if not q["wall"] or q["kind"] != "own": continue
        dq, nq, Lq = geo(q)
        if nq.dot(n) > -0.8: continue
        A = v2(q["A"]); t = (P2 - A).dot(dq)
        if t < -2 or t > Lq + 2: continue
        dist = (P2 - A).dot(nq)
        if dist < -1.0: continue
        if best is None or dist < best[0]: best = (dist, q)
    return best

def detect_shared(N, Ow):
    out = []
    for r in N.recs:
        if not r["wall"]: out.append(r); continue
        L = geo(r)[2]
        def f(t, r=r):
            g = gap_at(v2(r["A"] + (r["B"] - r["A"]) * t), r, Ow); return g is not None and g[0] < GAP_SHARED
        ts = [k / 40 for k in range(41)]; fl = [f(t) for t in ts]; cuts = []
        for k in range(40):
            if fl[k] != fl[k + 1]:
                lo, hi = ts[k], ts[k + 1]
                for _ in range(30):
                    m = (lo + hi) / 2
                    if f(m) == fl[k]: lo = m
                    else: hi = m
                c = (lo + hi) / 2
                if 1.0 < c * L < L - 1.0: cuts.append(c)
        segs = []; rr = r; prev = 0.0
        for c in cuts:
            a, b = split_rec(rr, (c - prev) / (1 - prev)); segs.append(a); rr = b; prev = c
        segs.append(rr)
        for s in segs:
            mid = v2(s["A"] + (s["B"] - s["A"]) * 0.5); gp = gap_at(mid, s, Ow)
            if gp and gp[0] < GAP_SHARED and geo(s)[2] >= MIN_RUN:
                s["kind"] = "shared"; s["owner"] = Ow.name
                for k in range(5):
                    g2 = gap_at(v2(s["A"] + (s["B"] - s["A"]) * ((k + 0.5) / 5)), s, Ow)
                    if g2: g2[1].setdefault("gaps", []).append(g2[0])
            out.append(s)
    N.recs = out

def apply_sh(Ow):
    R = Ow.recs
    for r in R:
        gs = r.get("gaps")
        if gs and Ow.name in CENTRAR:
            gm = sorted(gs)[len(gs) // 2]; r["sh"] = (gm - T) / 2 if gm >= T + 0.05 else 0.0
    for r in R:
        if r.get("sh", 0) > 0:
            d, n, L = geo(r)
            for k in ("A", "B"):
                X = v2(r[k]) + n * r["sh"]; r[k] = Vector((X.x, X.y, ztop(Ow, r["g"], X)))
    for i in range(len(R)):
        p, c = R[i - 1], R[i]
        if p.get("sh", 0) > 0 or c.get("sh", 0) > 0:
            dp, dc = geo(p)[0], geo(c)[0]
            X = line_x(v2(p["A"]), dp, v2(c["A"]), dc) if abs(cross2(dp, dc)) > 0.05 else None
            if X is None: X = (v2(p["B"]) + v2(c["A"])) / 2
            if True: p["B"] = Vector((X.x, X.y, ztop(Ow, p["g"], X))); c["A"] = Vector((X.x, X.y, ztop(Ow, c["g"], X)))

for N_, Ow_ in PAIRS:
    if N_ in TR and Ow_ in TR: detect_shared(TR[N_], TR[Ow_])
for nm in TR:
    if partners_of(nm): apply_sh(TR[nm])
rep["sh"] = {nm: sorted({round(r.get("sh", 0), 2) for r in TR[nm].recs if r.get("gaps")}) for nm in TR if partners_of(nm)}

def outer_chains(tr):
    R = tr.recs; n = len(R)
    st = next((i for i, r in enumerate(R) if not (r["wall"] and r["kind"] == "own")), 0)
    chains = []; cur = []
    for k in range(1, n + 1):
        r = R[(st + k) % n]
        if r["wall"] and r["kind"] == "own": cur.append(r)
        elif cur: chains.append(cur); cur = []
    if cur: chains.append(cur)
    out = []
    for ch in chains:
        L = [(v2(r["A"]) + geo(r)[1] * T, geo(r)[0], r) for r in ch]
        pts = [L[0][0]]
        for i in range(1, len(L)):
            X = line_x(L[i - 1][0], L[i - 1][1], L[i][0], L[i][1]); pts.append(X if X else L[i][0])
        pts.append(v2(ch[-1]["B"]) + geo(ch[-1])[1] * T)
        cum = [0.0]
        for i in range(len(pts) - 1): cum.append(cum[-1] + (pts[i + 1] - pts[i]).length)
        out.append(dict(pts=pts, recs=[x[2] for x in L], cum=cum, tray=tr.name))
    return out

def proj_poly(P, pl):
    best = None
    for k in range(len(pl["pts"]) - 1):
        a, b = pl["pts"][k], pl["pts"][k + 1]; dd, t = seg_dist(P, a, b)
        if best is None or dd < best[0]: best = (dd, k, t, a + (b - a) * t, pl["cum"][k] + t * (b - a).length)
    return best
def pt_at(pl, s):
    for k in range(len(pl["pts"]) - 1):
        if pl["cum"][k] - 1e-9 <= s <= pl["cum"][k + 1] + 1e-9:
            L = pl["cum"][k + 1] - pl["cum"][k]; t = 0 if L < 1e-9 else (s - pl["cum"][k]) / L
            return pl["pts"][k] + (pl["pts"][k + 1] - pl["pts"][k]) * t, k
    return (pl["pts"][0], 0) if s < 0 else (pl["pts"][-1], len(pl["pts"]) - 2)
def sub_poly(pl, s0, s1):
    sg = 1 if s1 >= s0 else -1
    inner = [(pl["cum"][k], k) for k in range(1, len(pl["pts"]) - 1) if min(s0, s1) < pl["cum"][k] < max(s0, s1)]
    inner.sort(key=lambda x: sg * x[0])
    ss = [s0] + [c for c, k in inner] + [s1]
    pts = [pt_at(pl, s)[0] for s in ss]
    recs = [pl["recs"][pt_at(pl, (ss[i] + ss[i + 1]) / 2)[1]] for i in range(len(ss) - 1)]
    return pts, recs, ss

for nm in TR: TR[nm].outer = outer_chains(TR[nm])

# ------------------------------------------------------------------ contorno del piso en planta
def build_lines(tr):
    R = tr.recs; n = len(R)
    st = next((i for i, r in enumerate(R) if r["kind"] == "free"), next((i for i, r in enumerate(R) if r["kind"] != "shared"), 0))
    R = R[st:] + R[:st]; tr.recs = R
    items = []; i = 0
    while i < n:
        if R[i]["kind"] == "shared":
            j = i
            while j < n and R[j]["kind"] == "shared": j += 1
            items.append(["run", R[i:j]]); i = j
        else: items.append(["rec", R[i]]); i += 1
    tr.wedges = []; tr.runs = []
    for k, it in enumerate(items):
        if it[0] != "run": continue
        x = it[1]; Ow = TR[x[0]["owner"]]
        Ps, Pe = v2(x[0]["A"]), v2(x[-1]["B"])
        pl = min(Ow.outer, key=lambda pl: proj_poly(Ps, pl)[0] + proj_poly(Pe, pl)[0])
        pts, orecs, ss = sub_poly(pl, proj_poly(Ps, pl)[4], proj_poly(Pe, pl)[4])
        run = dict(pts=pts, orecs=orecs, owner=Ow.name, recs=x, steps=[None, None], pl=pl, ss=ss)
        it[1] = run; tr.runs.append(run)
        for side in (0, 1):
            t2, nb = items[(k - 1) % len(items)] if side == 0 else items[(k + 1) % len(items)]
            if t2 != "rec": continue
            dn = geo(nb)[0]
            dr = norm2(pts[1] - pts[0]) if side == 0 else norm2(pts[-1] - pts[-2]); Q = pts[0] if side == 0 else pts[-1]
            ang = math.degrees(math.acos(min(1.0, abs(dn.dot(dr)))))
            if nb["wall"] and ang < SHALLOW:
                run["steps"][side] = dict(rec=nb, ang=ang)
                S = v2(nb["B"]) if side == 0 else v2(nb["A"])
                Lw = T / math.tan(math.radians(max(ang, 2.0)))
                s_q = ss[0] if side == 0 else ss[-1]; sgn = (1 if ss[-1] >= ss[0] else -1) * (1 if side == 0 else -1)
                W0 = pt_at(pl, s_q + sgn * Lw)[0]
                tr.wedges.append(dict(S=S, Sc=Q, W0=W0, ang=ang, rec=nb, owner=Ow.name, Lw=Lw))
            else:
                X = line_x(v2(nb["A"]), dn, Q + perp(dr) * 0.3, dr)
                if X is not None and (X - Q).length < 30:
                    key = "B" if side == 0 else "A"; nb[key] = Vector((X.x, X.y, ztop(tr, nb["g"], X)))
    L = []
    for typ, x in items:
        if typ == "rec":
            r = x; d, nn, Lr = geo(r)
            if r["wall"]:
                wf = wallframe(tr, r["g"], r["A"], r["B"], Vector((nn.x, nn.y, 0.0)))
                L.append(dict(p=v2(r["A"]) - v2(wf["u3"]) * wf["e_off"], d=d, kind="wall", rec=r, wf=wf, v=v2(r["A"])))
            else: L.append(dict(p=v2(r["A"]), d=d, kind="free", rec=r, v=v2(r["A"])))
        else:
            run = x; P = run["pts"]
            if run["steps"][0]:
                nb = run["steps"][0]["rec"]; dn, nn, _ = geo(nb)
                lean = T * abs(tr.G[grp_at(tr, v2(nb["B"]) + dn * 2.0)]["n"].dot(Vector((dn.x, dn.y, 0))))
                L.append(dict(p=v2(nb["B"]) + dn * (C_PISO + lean), d=nn, kind="step", v=v2(nb["B"])))
            for k in range(len(P) - 1):
                if (P[k + 1] - P[k]).length < 0.05: continue
                d = norm2(P[k + 1] - P[k]); nw = Vector((d.y, -d.x, 0.0))
                g = grp_at(tr, (P[k] + P[k + 1]) / 2 - v2(nw) * 3.0)
                A3, B3 = P3(tr, P[k], g), P3(tr, P[k + 1], g)
                wf = wallframe(tr, g, A3, B3, nw)
                L.append(dict(p=P[k] - v2(wf["u3"]) * wf["e_off"], d=d, kind="shared", run=run, A2=P[k], B2=P[k + 1],
                              g=g, wf=wf, orec=run["orecs"][k], v=P[k]))
            if run["steps"][1]:
                nb = run["steps"][1]["rec"]; dn, nn, _ = geo(nb)
                lean = T * abs(tr.G[grp_at(tr, v2(nb["A"]) - dn * 2.0)]["n"].dot(Vector((dn.x, dn.y, 0))))
                L.append(dict(p=v2(nb["A"]) - dn * (C_PISO + lean), d=-nn, kind="step", v=v2(nb["A"])))
    C = []
    for i in range(len(L)):
        a, b = L[i - 1], L[i]
        X = line_x(a["p"], a["d"], b["p"], b["d"]) if abs(cross2(a["d"], b["d"])) > 0.05 else None
        if X is None or (X - b["p"]).length > 300:     # casi paralelas: proyectar el vertice comun en ambas rectas
            v = b["v"]; X = ((a["p"] + a["d"] * (v - a["p"]).dot(a["d"])) + (b["p"] + b["d"] * (v - b["p"]).dot(b["d"]))) / 2
        C.append(X)
    tr.lines = L; tr.corners = C

for nm in TR: build_lines(TR[nm])
for nm in TR: TR[nm].outer = outer_chains(TR[nm])     # extremos ajustados en las transiciones

# ------------------------------------------------------------------ clasificacion de paredes
def shared_partner(tr, r, X):
    """X en la cara interior de una pared propia: devuelve la bandeja cuyo piso llega a su cara exterior"""
    n = geo(r)[1]; Q = X + n * T
    for nm, own in PAIRS:
        if own != tr.name or nm not in TR: continue
        for run in TR[nm].runs:
            if run["owner"] != tr.name: continue
            P = run["pts"]
            if any(seg_dist(Q, P[k], P[k + 1])[0] < 0.8 for k in range(len(P) - 1)): return TR[nm]
    return None
def free_at(tr, r, X):
    """distancia libre por fuera de la pared hasta la cara exterior de otra pared (o None)"""
    d, n, L = geo(r); o = X + n * T; best = None
    for nm, t2 in TR.items():
        if nm == tr.name: continue
        for pl in t2.outer:
            for k in range(len(pl["pts"]) - 1):
                a, b = pl["pts"][k], pl["pts"][k + 1]; db = b - a
                if db.length < 1e-6: continue
                nb = Vector((db.y, -db.x)).normalized()
                if nb.dot(n) > -0.5: continue
                den = cross2(n, db)
                if abs(den) < 1e-9: continue
                tt = cross2(a - o, db) / den; uu = cross2(a - o, n) / den
                if -0.5 <= tt <= GAP_WALL and -0.02 <= uu <= 1.02:
                    if best is None or tt < best[0]: best = (tt, nm, a + db * uu)
    return best
for tr in TR.values():
    for r in tr.recs:
        if r["wall"] and r["kind"] == "own":
            d, n, L = geo(r)
            fr = [free_at(tr, r, v2(r["A"]) + d * (L * t)) for t in (0.2, 0.5, 0.8)]
            r["gapwall"] = any(f is not None for f in fr)

# ------------------------------------------------------------------ escaneo de obstaculos (escuadras)
_dg = bpy.context.evaluated_depsgraph_get(); _sc = bpy.context.scene
def hit_obj(org_mm, dir3, dist_mm):
    org = org_mm / 1000.0; left = dist_mm / 1000.0
    for _ in range(12):
        ok, loc, n_, i_, ob, m_ = _sc.ray_cast(_dg, org, dir3, distance=left)
        if not ok: return None
        if not ob.name.startswith(IGNORAR): return ob.name
        left -= (loc - org).length + 0.0002; org = loc + dir3 * 0.0002
        if left <= 0: return None
    return None
def blocked_at(tr, r, p):
    d, n, L = geo(r); P2 = v2(r["A"]) + d * p; zf = zbot(tr, r["g"], P2); DEP = CLIP_T + 0.8
    for t in (0.25, 2.5, 4.75, T + 1.0, T + CLIP_T, -2.0, -6.0, -10.0, -(CLIP_H - T)):
        Pt = P2 + n * t; g = r["g"] if t > 0 else grp_at(tr, Pt)
        h = hit_obj(Vector((Pt.x, Pt.y, zbot(tr, g, Pt) - 0.05)), Vector((0, 0, -1)), DEP)
        if h: return h
    d3 = Vector((n.x, n.y, 0.0)); zz = zf - DEP
    while zz < zf + CLIP_V:
        h = hit_obj(Vector((P2.x, P2.y, zz)), d3, T + CLIP_T + 0.5)
        if h: return h
        zz += 1.0
    return None
def zones(tr, r):
    if "zones" in r: return r["zones"]
    L = geo(r)[2]; z = []; cur = None; k = 0
    while k <= L:
        h = blocked_at(tr, r, k)
        if h:
            if cur is None: cur = [k, k, h]
            cur[1] = k
        elif cur is not None: z.append(cur); cur = None
        k += 1.0
    if cur is not None: z.append(cur)
    r["zones"] = [[a - 2.0, b + 2.0, o] for a, b, o in z]
    return r["zones"]

# ------------------------------------------------------------------ pestanas
for tr in TR.values():
    tr.tabs = []
    for li, ln in enumerate(tr.lines):
        if ln["kind"] != "wall": continue
        r = ln["rec"]; d, n, L = geo(r)
        if L < TAB_MIN_SEG: continue
        nt = max(1, round(L / TAB_PASO))
        for k in range(nt):
            p = L * (k + 0.5) / nt; X = v2(r["A"]) + d * p
            partner = shared_partner(tr, r, X)
            kind = "closed" if (partner or r["gapwall"]) else "open"
            if kind == "open":
                for na, nb, ob_ in zones(tr, r):
                    lo_p, hi_p = na - W_TAB / 2 - 4.0, nb + W_TAB / 2 + 4.0
                    if lo_p < p < hi_p:
                        cand = [c for c in (lo_p, hi_p) if W_TAB / 2 + 8 <= c <= L - W_TAB / 2 - 8]
                        if cand: p = min(cand, key=lambda c: abs(c - p))
                        else: aviso(f"{tr.name}: pestana sin lugar libre para escuadra ({ob_})"); kind = "nobracket"
                X = v2(r["A"]) + d * p
            if kind == "closed":
                def ok_at(pp):
                    for u in range(-int(W_TAB / 2) - 3, int(W_TAB / 2) + 4, 2):
                        Xq = v2(r["A"]) + d * (pp + u); zf_ = zbot(tr, r["g"], Xq)
                        if hit_obj(Vector((Xq.x + n.x * T / 2, Xq.y + n.y * T / 2, zf_ - 0.05)), Vector((0, 0, -1)), M_SLOT + 0.5): return False
                    return True
                if not ok_at(p):
                    cand = [pp for k_ in range(1, 120) for pp in (p + k_, p - k_) if W_TAB / 2 + 8 <= pp <= L - W_TAB / 2 - 8]
                    best_ = next((pp for pp in cand if ok_at(pp)), None)
                    if best_ is None: aviso(f"{tr.name}: pestana cerrada sobre el bastidor, sin lugar")
                    else: p = best_
            J3 = r["A"] + (r["B"] - r["A"]) * (p / L)
            if any(t_["rec"] is r and abs((v2(t_["J3"]) - v2(r["A"])).dot(d) - p) < W_TAB + 4 for t_ in tr.tabs): continue
            tr.tabs.append(dict(line=li, rec=r, J3=J3, wf=ln["wf"], g=r["g"], kind=kind, wallrec=r, tray=tr,
                                dist=(v2(J3) - tr.corners[li]).dot(ln["d"]), partner=partner.name if partner else None))
# pestanas de los pisos vecinos en paredes compartidas (despues de las del dueno)
for tr in TR.values():
    for li, ln in enumerate(tr.lines):
        if ln["kind"] != "shared": continue
        Ow = TR[ln["run"]["owner"]]; A2, B2 = ln["A2"], ln["B2"]; d = ln["d"]; L = (B2 - A2).length
        if L < TAB_MIN_SEG: continue
        busy = [(v2(t["J3"]) - A2).dot(d) for t in Ow.tabs if (lambda dd: dd[0] < T + 3)(seg_dist(v2(t["J3"]), A2 - perp(d) * 0 , B2))]
        busy = [(v2(t["J3"]) - A2).dot(d) for t in Ow.tabs if seg_dist(v2(t["J3"]) + geo(t["rec"])[1] * T, A2, B2)[0] < 1.0]
        nw2 = Vector((d.y, -d.x))
        def sh_ok(pp, A2=A2, d=d, nw2=nw2, g=ln["g"]):
            for u in range(-int(W_TAB / 2) - 3, int(W_TAB / 2) + 4, 2):
                Xq = A2 + d * (pp + u); zf_ = zbot(tr, g, Xq) - 0.05; Yq = Xq + nw2 * (T / 2)
                if hit_obj(Vector((Yq.x, Yq.y, zf_)), Vector((0, 0, -1)), M_SLOT + 0.5): return False
            return True
        nt = max(1, round(L / TAB_PASO))
        for k in range(nt):
            p0 = L * (k + 0.5) / nt; best = None
            for dk in range(0, 200):
                for p in (p0 + dk * 1.0, p0 - dk * 1.0):
                    if W_TAB / 2 + 8 <= p <= L - W_TAB / 2 - 8 and all(abs(p - b) >= W_TAB + 6 for b in busy) and sh_ok(p): best = p; break
                if best is not None: break
            if best is None: aviso(f"{tr.name}: pestana en pared compartida sin lugar"); continue
            X = A2 + d * best; J3 = P3(tr, X, ln["g"]); busy.append(best)
            tr.tabs.append(dict(line=li, rec=None, J3=J3, wf=ln["wf"], g=ln["g"], kind="shared", wallrec=ln["orec"], tray=tr,
                                dist=(X - tr.corners[li]).dot(d), owner=Ow.name))

# ------------------------------------------------------------------ desarrollo del piso
def to2d(tf, P): q = P - tf["O3"]; return tf["o2"] + tf["ex2"] * q.dot(tf["ex3"]) + tf["ey2"] * q.dot(tf["ey3"])
def to3d(tf, q): w = q - tf["o2"]; return tf["O3"] + tf["ex3"] * w.dot(tf["ex2"]) + tf["ey3"] * w.dot(tf["ey2"])
def unfold(tr):
    G = tr.G; root = max(range(len(G)), key=lambda k: G[k]["area"]); tf = [None] * len(G)
    n = G[root]["n"]; P = [tr.V[i] for i in G[root]["loop"]]
    ex3 = P[1] - P[0]; ex3 = (ex3 - n * ex3.dot(n)).normalized()
    tf[root] = dict(O3=G[root]["c"], ex3=ex3, ey3=n.cross(ex3), o2=Vector((0, 0)), ex2=Vector((1, 0)), ey2=Vector((0, 1)))
    todo = [root]; used = set()
    while todo:
        g = todo.pop(0)
        for fi, f in enumerate(tr.folds):
            if fi in used or g not in (f["g1"], f["g2"]): continue
            h = f["g2"] if f["g1"] == g else f["g1"]
            if tf[h] is not None: aviso(f"{tr.name}: el piso tiene un ciclo de pliegues"); used.add(fi); continue
            used.add(fi)
            a2, b2 = to2d(tf[g], f["A"]), to2d(tf[g], f["B"]); ex2 = norm2(b2 - a2)
            nh = G[h]["n"]; ch = G[h]["c"]
            Ah = f["A"] - nh * (f["A"] - ch).dot(nh); Bh = f["B"] - nh * (f["B"] - ch).dot(nh)
            e = (Bh - Ah).normalized()
            tf[h] = dict(O3=Ah, ex3=e, ey3=nh.cross(e), o2=a2, ex2=ex2, ey2=perp(ex2)); todo.append(h)
    tr.tf = tf
def map2(tr, X, g=None):
    g = grp_at(tr, X) if g is None else g
    return to2d(tr.tf[g], P3(tr, X, g))

CLIPS = []      # escuadras (todas las bandejas)
def dedup(lp):
    out = []
    for p in lp:
        if not out or (p - out[-1]).length > 1e-5: out.append(p)
    while len(out) > 1 and (out[0] - out[-1]).length <= 1e-5: out.pop()
    return out
def split_by_chord(poly, a, b):
    """divide el poligono por la cuerda de la recta a-b que contiene el tramo a-b"""
    d = b - a; hits = []; n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]; e = q - p; den = cross2(d, e)
        if abs(den) < 1e-12: continue
        t = cross2(p - a, e) / den; u = cross2(p - a, d) / den
        if -1e-7 <= u <= 1 + 1e-7: hits.append((t, i))
    lo = [h for h in hits if h[0] <= 0.5]; hi = [h for h in hits if h[0] > 0.5]
    if not lo or not hi: return [poly]
    (t1, i1), (t2, i2) = max(lo), min(hi)
    if i1 == i2: return [poly]
    P1, P2 = a + d * t1, a + d * t2
    def walk(i_from, P_from, i_to, P_to):
        out = [P_from]; k = (i_from + 1) % n
        while True:
            out.append(poly[k])
            if k == i_to: break
            k = (k + 1) % n
        out.append(P_to); return out
    return [walk(i1, P1, i2, P2), walk(i2, P2, i1, P1)]
def lift(tr, X, g): return Vector((X.x, X.y, ztop(tr, g, X)))
def floor_g(tr, X):
    for g, rg in getattr(tr, "regions", []):
        if inside2(X, rg): return g
    return grp_at(tr, X)
for tr in TR.values():
    unfold(tr)
    C = tr.corners; Ls = tr.lines; plan = []
    for i, ln in enumerate(Ls):
        c0, c1 = C[i], C[(i + 1) % len(C)]
        plan.append(c0); extra = []; dd = c1 - c0
        for fo in tr.folds:
            fa, fb = v2(fo["A"]), v2(fo["B"]); df = fb - fa; den = cross2(dd, df)
            if abs(den) < 1e-9: continue
            t = cross2(fa - c0, df) / den; u = cross2(fa - c0, dd) / den; Lf = df.length
            if 1e-4 < t < 1 - 1e-4 and -25.0 / Lf < u < 1 + 25.0 / Lf: extra.append(((dd * t).length, [c0 + dd * t]))
        for tb in tr.tabs:
            if tb["line"] != i: continue
            wf = tb["wf"]; e3 = wf["e3"] if v2(wf["e3"]).dot(ln["d"]) > 0 else -wf["e3"]; u3 = wf["u3"]
            Jin = tb["J3"] - u3 * wf["e_off"]
            A_ = Jin - e3 * (W_TAB / 2); D_ = Jin + e3 * (W_TAB / 2)
            B_ = A_ + u3 * (wf["e_off"] + wf["lend"]); C_ = D_ + u3 * (wf["e_off"] + wf["lend"])
            extra.append(((v2(Jin) - c0).dot(ln["d"]), [v2(q) for q in (A_, B_, C_, D_)]))
        for _, ps in sorted(extra, key=lambda x: x[0]): plan += ps
    plan = dedup(plan); tr.floor_plan = plan
    regs = [list(plan)]
    for fo in tr.folds:
        a, b = v2(fo["A"]), v2(fo["B"]); m = (a + b) / 2
        for k, rg in enumerate(regs):
            if inside2(m, rg): regs[k:k + 1] = split_by_chord(rg, a, b); break
        else: aviso(f"{tr.name}: pliegue fuera del piso")
    tr.regions = []
    for rg in regs:
        rg = dedup(rg)
        if len(rg) < 3 or abs(area2(rg)) < 1e-3: continue
        c = sum(rg, Vector((0, 0))) / len(rg)
        g = next((g for g in range(len(tr.G)) if inside2(c, tr.G[g]["plan"])), None)
        if g is None: g = min(range(len(tr.G)), key=lambda g: poly_dist(c, tr.G[g]["plan"]))
        tr.regions.append((g, rg))
    def g_of(X, probe):
        for g, rg in tr.regions:
            if inside2(probe, rg): return g
        return grp_at(tr, X)
    pts2 = []; n = len(plan)
    for i, X in enumerate(plan):
        a, b = plan[i - 1], plan[(i + 1) % n]; nin = Vector((0, 0))
        if (X - a).length > 1e-9: nin += perp(norm2(X - a))
        if (b - X).length > 1e-9: nin += perp(norm2(b - X))
        probe = X + norm2(nin) * 0.05 if nin.length > 1e-9 else X
        g = g_of(X, probe); pts2.append(to2d(tr.tf[g], lift(tr, X, g)))
    tr.floor2d = dogbone(pts2, hole=False, min_turn=45.0)

# ------------------------------------------------------------------ paredes: cadenas y piezas
def ceil_bvh(tr):
    vs = []; ps = []
    for nm, t2 in TR.items():
        if nm == tr.name: continue
        ob = O[nm]; base = len(vs)
        vs += [(ob.matrix_world @ v.co) * 1000.0 for v in ob.data.vertices]
        for p in ob.data.polygons:
            if abs(newell([vs[base + i] for i in p.vertices]).z) > 0.3: ps.append([base + i for i in p.vertices])
    return BVHTree.FromPolygons(vs, ps)
def ceil_at(tr, X, z0):
    hit = tr.ceil.ray_cast(Vector((X.x, X.y, z0)), Vector((0, 0, 1)), 200.0)
    if hit[0] is None: return None
    nz = abs(hit[1].z) if hit[1] is not None else 1.0
    return hit[0].z - T / max(nz, 0.3) - 0.5


for tr in TR.values(): tr.ceil = ceil_bvh(tr)

def s_of(seg, P): return seg["S"] + seg["a0"] + (v2(P) - v2(seg["C0"])).dot(seg["d"])

def make_pieces(tr):
    R = tr.recs; n = len(R)
    st = next((i for i, r in enumerate(R) if not (r["wall"] and r["kind"] == "own")), None)
    if st is None: st = 0; aviso(f"{tr.name}: pared cerrada sin corte")
    chains = []; cur = []
    for k in range(1, n + 1):
        r = R[(st + k) % n]
        if r["wall"] and r["kind"] == "own" and geo(r)[2] > 0.3: cur.append(r)
        elif cur: chains.append(cur); cur = []
    if cur: chains.append(cur)
    out = []
    for ch in chains:
        corners = []
        for i in range(len(ch) - 1):
            d0, n0, _ = geo(ch[i]); d1, n1, _ = geo(ch[i + 1])
            corners.append(dict(i=i, ang=math.degrees(math.acos(max(-1, min(1, d0.dot(d1))))), concava=d1.dot(n0) < 0))
        sig = [c for c in corners if c["ang"] >= FLAT_TURN]; splits = set()
        for a, b in zip(sig[:-1], sig[1:]):
            if a["concava"] != b["concava"]: splits.add((a if a["concava"] else b)["i"])
        def plen(a, b): return sum(geo(r)[2] for r in ch[a:b + 1])
        changed = True
        while changed:
            changed = False; cut = sorted(splits); bnds = [-1] + cut + [len(ch) - 1]
            for k in range(len(bnds) - 1):
                a, b = bnds[k] + 1, bnds[k + 1]
                if plen(a, b) < 20.0:
                    cand = [c for c in (bnds[k], bnds[k + 1]) if c in splits and corners[c]["ang"] <= 25.0]
                    if cand: splits.discard(min(cand, key=lambda c: corners[c]["ang"])); changed = True; break
        start = 0; parts = []
        for c in sorted(splits): parts.append((start, c)); start = c + 1
        parts.append((start, len(ch) - 1))
        for a, b in parts:
            cs = [dict(c, i=c["i"] - a) for c in corners if a <= c["i"] < b]
            sg = [c for c in cs if c["ang"] >= FLAT_TURN]
            cara = "A" if (sg and sg[0]["concava"]) else "B"
            segs = []
            for r in ch[a:b + 1]:
                d, nn, L = geo(r); segs.append(dict(C0=r["A"], C1=r["B"], d=d, n=nn, L=L, rec=r, a0=0.0, a1=0.0))
            if cara == "A":      # piel por fuera: el desarrollo se mide en la cara exterior
                for c in cs:
                    aa = T * math.tan(math.radians(c["ang"] / 2)) * (1 if c["concava"] else -1)
                    segs[c["i"]]["a1"] = aa; segs[c["i"] + 1]["a0"] = aa
            S = 0.0
            for s in segs: s["S"] = S; s["flat"] = s["L"] + s["a0"] + s["a1"]; S += s["flat"]
            s0 = segs[0]; right = Vector((s0["n"].y, -s0["n"].x))
            vista_dentro = s0["d"].dot(right) > 0
            out.append(dict(segs=segs, corners=cs, cara=cara, S=S, tray=tr.name, slots=[], holes=[], notches=[],
                            mirror=vista_dentro if cara == "B" else not vista_dentro))
    k = 0
    for pc in out:
        vis = {i for s in pc["segs"] for i in s["rec"]["vi"]}
        nm = next((v for key, v in CENTRAL_NAMES.items() if key in vis), None) if tr.name == "BandejaCentral" else None
        if nm is None: k += 1; nm = f"Pared_{k}"
        pc["name"] = nm
    return out

def seg_of(tr, rec):
    for pc in tr.pieces:
        for s in pc["segs"]:
            if s["rec"] is rec: return pc, s
    return None, None
def seg_near(tr, X):
    best = None
    for pc in tr.pieces:
        for s in pc["segs"]:
            dd, t = seg_dist(X, v2(s["C0"]), v2(s["C1"]))
            if best is None or dd < best[0]: best = (dd, pc, s)
    return best[1], best[2]

def deep_ok(X, n, z0, z1, d=None):
    """no hay piezas de la maquina entre z0 y z1 bajo la huella de la pared"""
    d = Vector((-n.y, n.x)) if d is None else d
    for e in (0.3, T / 2, T - 0.3):
        for a in (-1.5, 0.0, 1.5):
            Y = X + n * e + d * a
            if hit_obj(Vector((Y.x, Y.y, z0)), Vector((0, 0, -1)), z0 - z1 + 0.5): return False
    return True
def seg_bottom(tr, seg, X):
    r = seg["rec"]; g = r["g"]; n = seg["n"]
    z = max(zbot(tr, g, X), zbot(tr, g, X + n * T))
    zz = seg_bottom_deep(tr, seg, X, z)
    if zz < z - 1e-6 and not deep_ok(X, n, z - 0.05, zz):
        rep.setdefault("muescas_bastidor", set()).add(f"{tr.name}{r['vi']}")
        return z
    return zz
def seg_bottom_deep(tr, seg, X, z):
    r = seg["rec"]; n = seg["n"]
    part = shared_partner(tr, r, X)
    if part is not None:
        Q = X + n * (T + 0.3); zz = min(z, zbot(part, floor_g(part, Q), Q)) - M_SLOT
        dd = geo(r)[0]; poly = part.corners
        for Y in [X + n * e + dd * a for e in (0.0, T / 2, T - 0.2) for a in (-3.0, -1.5, 0.0, 1.5, 3.0)]:
            if inside2(Y, poly): zz = max(zz, ztop(part, floor_g(part, Y), Y) + 0.5)
        return zz
    if r.get("gapwall"):
        zz = z - M_SLOT
        # al bajar M_SLOT no debe atravesar el piso de otra bandeja que pase por debajo (con 4 mm ocurre al final de
        # los tramos compartidos): se apoya 0.5 mm sobre ese piso. Se revisa todo el espesor, hasta la cara exterior.
        dd = geo(r)[0]
        for t2 in TR.values():
            if t2 is tr: continue
            for Y in [X + n * e + dd * a for e in (0.05, T / 2, T - 0.6, T - 0.3, T - 0.05) for a in (-3.0, -1.5, 0.0, 1.5, 3.0)]:
                if inside2(Y, t2.corners):
                    zf2 = ztop(t2, floor_g(t2, Y), Y)
                    if zf2 < z + 1.0: zz = max(zz, zf2 + 0.5)
        return zz
    return z
def seg_top(tr, seg, X, p):
    r = seg["rec"]; dr, nr, Lr = geo(r); t = max(0.0, min(1.0, (X - v2(r["A"])).dot(dr) / max(Lr, 1e-9)))
    zt = r["ta"] + (r["tb"] - r["ta"]) * t; zf = ztop(tr, r["g"], X)
    YS = [X + seg["n"] * e + seg["d"] * a for e in (0.0, T / 2, T) for a in (-0.6, 0.0, 0.6)]
    for Y in YS:
        c = ceil_at(tr, Y, zf + 0.5)
        if c is not None and c < zt: zt = c
        for nm in ORDER[:ORDER.index(tr.name)]:
            bv = WALL_BVH.get(nm)
            if bv is None: continue
            h = bv.ray_cast(Vector((Y.x, Y.y, zf + 0.5)), Vector((0, 0, 1)), 200.0)
            if h[0] is not None and h[0].z - 0.5 < zt: zt = h[0].z - 0.5
    return zt
def simplify(pts, tol=0.02):
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        if (c - a).length > 1e-9 and abs(cross2(norm2(c - a), b - a)) < tol and (b - a).dot(c - b) >= 0: continue
        out.append(b)
    out.append(pts[-1]); return out
def z_at(poly, s):
    for a, b in zip(poly[:-1], poly[1:]):
        if a.x - 1e-9 <= s <= b.x + 1e-9: return a.y + (b.y - a.y) * (s - a.x) / max(b.x - a.x, 1e-12)
    return poly[0].y if s < poly[0].x else poly[-1].y

def clip_strip(poly, lo, hi, axis):
    def clip(P, keep, inter):
        out = []
        for i in range(len(P)):
            a, b = P[i - 1], P[i]; ka, kb = keep(a), keep(b)
            if kb:
                if not ka: out.append(inter(a, b))
                out.append(b)
            elif ka: out.append(inter(a, b))
        return out
    for lim, sgn in ((lo, 1), (hi, -1)):
        poly = clip(poly, lambda p, lim=lim, sgn=sgn: sgn * (p[axis] - lim) >= -1e-9,
                    lambda a, b, lim=lim: a + (b - a) * ((lim - a[axis]) / (b[axis] - a[axis])))
        if not poly: return []
    return poly
for tr in TR.values():
    tr.pieces = make_pieces(tr)
    for pc in [p for p in tr.pieces if sum(s_["L"] for s_ in p["segs"]) < 5.0]:
        aviso(f"{tr.name}/{pc['name']}: pieza de pared de {sum(s_['L'] for s_ in pc['segs']):.1f} mm descartada (demasiado corta)")
        tr.pieces.remove(pc)
        for tb in tr.tabs:
            if any(tb.get("rec") is s_["rec"] for s_ in pc["segs"]): tb["kind"] = "huerfana"

def restack(pc):
    S = 0.0
    for s in pc["segs"]: s["S"] = S; s["flat"] = s["L"] + s["a0"] + s["a1"]; S += s["flat"]
    pc["S"] = S
def profile(tr, pc):
    B = {}; Tp = {}
    def put(s, zb, zt):
        k = round(s, 4); B[k] = max(B.get(k, -1e9), zb); Tp[k] = min(Tp.get(k, 1e9), zt)
    for i, seg in enumerate(pc["segs"]):
        L = seg["L"]; ns = max(2, int(L / 1.0))
        for k in range(ns + 1):
            p = L * k / ns; X = v2(seg["C0"]) + seg["d"] * p
            put(seg["S"] + seg["a0"] + p, seg_bottom(tr, seg, X), seg_top(tr, seg, X, p))
        if i < len(pc["segs"]) - 1:
            X = v2(seg["C1"]); nx = pc["segs"][i + 1]
            put(seg["S"] + seg["flat"], max(seg_bottom(tr, seg, X), seg_bottom(tr, nx, X)),
                min(seg_top(tr, seg, X, L), seg_top(tr, nx, X, 0.0)))
    ks = sorted(B)
    if ks[0] > 1e-6: put(0.0, B[ks[0]], Tp[ks[0]])
    if ks[-1] < pc["S"] - 1e-6: put(pc["S"], B[ks[-1]], Tp[ks[-1]])
    ks = sorted(B)
    pc["bot"] = simplify([Vector((k, B[k])) for k in ks]); pc["top"] = simplify([Vector((k, Tp[k])) for k in ks])

# perfiles, en orden de arriba hacia abajo: las paredes ya calculadas hacen de techo para las siguientes
_PISO_SUP = {}
def piso_sup(t2):
    """BVH de la cara superior del piso de t2 (con pestanas) y cuadrilateros de sus pestanas en planta"""
    if t2.name in _PISO_SUP: return _PISO_SUP[t2.name]
    vs = []; fs = []
    for g, poly in t2.regions:
        base = len(vs); vs += [lift(t2, q, g) for q in poly]
        for tri in tessellate_polygon([[Vector((q.x, q.y, 0)) for q in poly]]): fs.append(tuple(base + k for k in tri))
    tabs = []
    for tb in t2.tabs:
        ln = t2.lines[tb["line"]]; wf = tb["wf"]; e3 = wf["e3"] if v2(wf["e3"]).dot(ln["d"]) > 0 else -wf["e3"]; u3 = wf["u3"]
        Jin = tb["J3"] - u3 * wf["e_off"]; ext = wf["e_off"] + wf["lend"] + 1.0
        A_ = Jin - e3 * (W_TAB / 2 + 0.5) - u3 * 0.5; D_ = Jin + e3 * (W_TAB / 2 + 0.5) - u3 * 0.5
        tabs.append([v2(A_), v2(A_ + u3 * ext), v2(D_ + u3 * ext), v2(D_)])
    _PISO_SUP[t2.name] = (BVHTree.FromPolygons(vs, fs), tabs); return _PISO_SUP[t2.name]

def apoyar_sobre_pisos(tr, pc, paso=0.25):
    """el borde inferior de la pared no debe atravesar el piso de OTRA bandeja (salvo sus pestanas, que entran en
    ranuras). Rayos verticales cada 0.25 mm en todo el espesor: donde un piso ajeno queda por encima del borde
    inferior, la pared se apoya 0.5 mm sobre el. (El muestreo de profile() cada 1 mm se saltaba esquinas de pisos
    inclinados.)"""
    otros = [piso_sup(t2) for t2 in TR.values() if t2 is not tr]
    extra = {}
    for seg in pc["segs"]:
        s0 = seg["S"] + seg["a0"]; nst = max(2, int(seg["L"] / paso))
        for k in range(nst + 1):
            p = seg["L"] * k / nst; s = s0 + p; X = v2(seg["C0"]) + seg["d"] * p
            zl = z_at(pc["bot"], s); zt = z_at(pc["top"], s); best = zl
            for bvh, tabs in otros:
                for j in range(13):
                    Y = X + seg["n"] * (0.05 + (T - 0.1) * j / 12)
                    if any(inside2(Y, q) for q in tabs): continue
                    h = bvh.ray_cast(Vector((Y.x, Y.y, zt - 1.0)), Vector((0, 0, -1)), (zt - 1.0) - (zl - T - 1.0))
                    if h[0] is None: continue
                    zf = h[0].z
                    if zf + 0.5 > best and zf < zt - 2.0: best = zf + 0.5
            if best > zl + 1e-4: extra[round(s, 4)] = best
    if not extra: return 0
    B = {round(q.x, 4): q.y for q in pc["bot"]}
    for k, v in extra.items(): B[k] = max(B.get(k, -1e9), v)
    pc["bot"] = simplify([Vector((k, max(B[k], z_at(pc["bot"], k)))) for k in sorted(B)])
    return len(extra)

ORDER = list(TR); WALL_BVH = {}
for tr in TR.values():
    _wc_v = []; _wc_f = []
    for pc in tr.pieces:
        profile(tr, pc)
        n_ap = apoyar_sobre_pisos(tr, pc)
        if n_ap: rep.setdefault("paredes_apoyadas_sobre_otro_piso", []).append(f"{tr.name}/{pc['name']}: {n_ap} puntos")
    for pc in tr.pieces:
        pc["outline"] = ccw(list(pc["top"]) + list(reversed(pc["bot"])))
        for s in pc["segs"]:
            lo, hi = s["S"], s["S"] + s["flat"]; part = clip_strip(list(pc["outline"]), lo, hi, 0)
            if len(part) < 3: continue
            def to3(q, s=s):
                P = v2(s["C0"]) + s["d"] * (q.x - s["S"] - s["a0"]); return Vector((P.x, P.y, q.y))
            base = len(_wc_v); m = len(part)
            _wc_v += [to3(q) for q in part] + [to3(q) + Vector((s["n"].x, s["n"].y, 0)) * T for q in part]
            for a, b, c in tessellate_polygon([[Vector((q.x, q.y, 0)) for q in part]]):
                _wc_f.append((base + a, base + b, base + c)); _wc_f.append((base + m + a, base + m + b, base + m + c))
            for i in range(m): _wc_f.append((base + i, base + (i + 1) % m, base + m + (i + 1) % m, base + m + i))
    WALL_BVH[tr.name] = BVHTree.FromPolygons(_wc_v, _wc_f)

# extremos de pared que chocan con paredes de otra bandeja: se recortan
def quad_of(seg, t0=0.0, t1=None):
    t1 = seg["L"] if t1 is None else t1; d, n = seg["d"], seg["n"]; e = 0.2
    a = v2(seg["C0"]) + d * (t0 + e); b = v2(seg["C0"]) + d * (t1 - e)
    return [a + n * e, b + n * e, b + n * (T - e), a + n * (T - e)]
def sat(P, Q):
    for poly in (P, Q):
        for i in range(len(poly)):
            e = poly[(i + 1) % len(poly)] - poly[i]; ax = Vector((-e.y, e.x))
            if ax.length < 1e-9: continue
            a = [p.dot(ax) for p in P]; b = [q.dot(ax) for q in Q]
            if max(a) < min(b) or max(b) < min(a): return False
    return True
def zr_at(pc, seg, P):
    sx = seg["S"] + seg["a0"] + max(0.0, min(seg["L"], (P - v2(seg["C0"])).dot(seg["d"])))
    return z_at(pc["bot"], sx), z_at(pc["top"], sx)
def zr_over(pc, seg, pts):
    """alturas de la pared (piso..borde) en la zona de seg que cae frente a los puntos pts"""
    us = [max(0.0, min(seg["L"], (p - v2(seg["C0"])).dot(seg["d"]))) for p in pts]
    s0, s1 = seg["S"] + seg["a0"] + min(us), seg["S"] + seg["a0"] + max(us)
    ss = [s0 + (s1 - s0) * k / 8 for k in range(9)]
    return min(z_at(pc["bot"], x) for x in ss), max(z_at(pc["top"], x) for x in ss)
def foreign(tr):
    return [(t2, pc, s) for t2 in TR.values() if t2.name != tr.name for pc in t2.pieces for s in pc["segs"]]
def conflicts(tr, pc, seg, t0, t1):
    sub = quad_of(seg, t0, t1); out = []
    pts = []; k = 0
    while t0 + k * 0.5 <= t1:
        for e in (0.3, T / 2, T - 0.3): pts.append(v2(seg["C0"]) + seg["d"] * (t0 + k * 0.5) + seg["n"] * e)
        k += 1
    for t2, pc2, s2 in foreign(tr):
        q2 = quad_of(s2)
        if not sat(sub, q2): continue
        for P in pts:
            if not inside2(P, q2): continue
            za = zr_at(pc, seg, P); zb = zr_at(pc2, s2, P)
            if za[0] < zb[1] - 0.6 and zb[0] < za[1] - 0.6: out.append((t2, pc2, s2)); break
    return out
def trim_need(tr, pc, at_start, only=None, maxt=30.0):
    seg = pc["segs"][0] if at_start else pc["segs"][-1]; L = seg["L"]
    def rng(t): return (t, min(L, t + maxt + 10)) if at_start else (max(0.0, L - t - maxt - 10), L - t)
    hits = [h for h in conflicts(tr, pc, seg, *rng(0.0)) if only is None or h[1] is only]
    if not hits: return 0.0, []
    t = 0.0
    while t <= min(maxt, L - 1.0):
        if not [h for h in conflicts(tr, pc, seg, *rng(t)) if only is None or h[1] is only]: return min(t + 1.0, L - 1.0), hits
        t += 0.25
    return None, hits
def do_trim(tr, pc, at_start, t):
    seg = pc["segs"][0] if at_start else pc["segs"][-1]
    if at_start:
        X = v2(seg["C0"]) + seg["d"] * t; seg["C0"] = Vector((X.x, X.y, ztop(tr, seg["rec"]["g"], X)))
    else:
        X = v2(seg["C1"]) - seg["d"] * t; seg["C1"] = Vector((X.x, X.y, ztop(tr, seg["rec"]["g"], X)))
    seg["L"] -= t; restack(pc); profile(tr, pc); apoyar_sobre_pisos(tr, pc)
    for tb in tr.tabs:
        if tb.get("rec") is seg["rec"]:
            u = (v2(tb["J3"]) - v2(seg["C0"])).dot(seg["d"])
            if u < W_TAB / 2 or u > seg["L"] - W_TAB / 2: aviso(f"{tr.name}/{pc['name']}: pestana dentro del extremo recortado")
rep["recortes"] = []
for _pasada, tr in [(k, t) for k in range(2) for t in reversed(list(TR.values()))]:
    for pc in tr.pieces:
        for at_start in (True, False):
            t, hits = trim_need(tr, pc, at_start)
            if not hits: continue
            best = (t, tr, pc, at_start) if t is not None else None
            for (t2, pc2, s2) in hits:          # quizas conviene recortar el extremo de la otra pieza
                for st2 in (True, False):
                    if s2 is not (pc2["segs"][0] if st2 else pc2["segs"][-1]): continue
                    tt, _ = trim_need(t2, pc2, st2, only=pc)
                    if tt is not None and tt > 0 and (best is None or tt < best[0]): best = (tt, t2, pc2, st2)
            if best is None: aviso(f"{tr.name}/{pc['name']}: extremo choca con otra bandeja y no se pudo recortar"); continue
            do_trim(best[1], best[2], best[3], best[0])
            rep["recortes"].append(f"{best[1].name}/{best[2]['name']} {'inicio' if best[3] else 'final'} -{best[0]:.2f} mm")

def clip_lejos(poly, Q, holg=0.2):
    """recorta poly para que quede a holg mm por fuera del cuadrilatero Q (lado de Q que mejor lo separa)"""
    cq = sum(Q, Vector((0, 0))) / len(Q); best = None
    for i in range(len(Q)):
        a, b = Q[i], Q[(i + 1) % len(Q)]; e = b - a
        if e.length < 1e-9: continue
        nout = Vector((e.y, -e.x)).normalized()
        if nout.dot(cq - a) > 0: nout = -nout
        sep = min((p - a).dot(nout) for p in poly) + max((p - a).dot(nout) for p in poly)
        if best is None or sep > best[0]: best = (sep, a, nout)
    _, a, nout = best; out = []
    f = lambda q: (q - a).dot(nout) - holg
    for i in range(len(poly)):
        p, q = poly[i - 1], poly[i]; fp, fq = f(p), f(q)
        if fq >= 0:
            if fp < 0: out.append(p + (q - p) * (fp / (fp - fq)))
            out.append(q)
        elif fp >= 0: out.append(p + (q - p) * (fp / (fp - fq)))
    return out
def area_abs(P): return abs(area2(P)) if len(P) >= 3 else 0.0
def _penetra(P, Q, holg=-0.02):
    """P invade Q mas de 0.02 mm (apoyarse contra la pared no cuenta)"""
    cq = sum(Q, Vector((0, 0))) / len(Q)
    for i in range(len(Q)):
        a, b = Q[i], Q[(i + 1) % len(Q)]; e = b - a
        if e.length < 1e-9: continue
        nout = Vector((e.y, -e.x)).normalized()
        if nout.dot(cq - a) > 0: nout = -nout
        if min((p - a).dot(nout) for p in P) >= holg: return False
    return sat(P, Q) or True                      # sin separacion suficiente por ningun lado de Q
def achica(P, k):
    c = sum(P, Vector((0, 0))) / len(P); return [c + (p - c) * k for p in P]
for tr in TR.values():
    keepw = []
    for w in tr.wedges:
        tri = [w["W0"], w["Sc"], w["S"]]; a0 = area_abs(tri)
        own = [s2 for pc2 in tr.pieces for s2 in pc2["segs"] if s2["rec"] is not w["rec"]]
        def huella(s2):
            a_, b_ = v2(s2["C0"]), v2(s2["C0"]) + s2["d"] * s2["L"]; return [a_, b_, b_ + s2["n"] * T, a_ + s2["n"] * T]
        q_ajenas = [huella(s2) for t2, pc2, s2 in foreign(tr)]; q_propias = [huella(s2) for s2 in own]
        quads = q_ajenas + q_propias
        # la cuna se recorta contra la pared que pisa (0.2 mm de holgura); si pierde mas del 40 % se descarta
        poly = list(tri)
        for _ in range(4):
            # paredes de otra bandeja: si la cuna entra mas de 0.02 mm se recorta con 0.2 mm de holgura; propias: como antes
            hit = [Q for Q in q_ajenas if _penetra(poly, Q)] + [Q for Q in q_propias if sat(achica(poly, 0.98), Q)]
            if not hit: break
            for Q in hit:
                poly = clip_lejos(poly, Q)
                if len(poly) < 3: break
            if len(poly) < 3: break
        if len(poly) < 3 or area_abs(poly) < 0.6 * a0 or any(sat(achica(poly, 0.98), Q) for Q in quads):
            aviso(f"{tr.name}: cuna PETG descartada (choca con una pared)"); continue
        if area_abs(poly) < a0 - 1e-6:
            w["poly"] = poly; rep.setdefault("cunas_recortadas", []).append(f"{tr.name}: queda {area_abs(poly) / a0 * 100:.0f} % de la cuna")
        keepw.append(w)
    tr.wedges = keepw

# ------------------------------------------------------------------ ranuras, muescas, escuadras
def slot_poly(seg, J3, wf):
    nf, e3, u3, nw = wf["nf"], wf["e3"], wf["u3"], wf["nw"]
    planes = [(nf, nf.dot(J3)), (-nf, -(nf.dot(J3) - T)), (e3, e3.dot(J3) + W_TAB / 2), (-e3, -(e3.dot(J3) - W_TAB / 2)),
              (u3, u3.dot(J3) + wf["lend"]), (-u3, -(u3.dot(J3) - wf["e_off"] - 2.0)), (nw, nw.dot(J3) + T), (-nw, -nw.dot(J3))]
    vs = []
    for i1 in range(8):
        for i2 in range(i1 + 1, 8):
            for i3 in range(i2 + 1, 8):
                Mx = Matrix((planes[i1][0], planes[i2][0], planes[i3][0]))
                if abs(Mx.determinant()) < 1e-9: continue
                X = Mx.inverted() @ Vector((planes[i1][1], planes[i2][1], planes[i3][1]))
                if all(pn.dot(X) <= pd + 1e-4 for pn, pd in planes): vs.append(X)
    return dogbone(offset_convex(hull([Vector((s_of(seg, X), X.z)) for X in vs]), C_SLOT), hole=True)

for tr in TR.values():
    for tb in tr.tabs:
        wf = tb["wf"]; J3 = tb["J3"]
        if tb["kind"] == "shared":
            Ow = TR[tb["owner"]]; pc, seg = seg_of(Ow, tb["wallrec"])
            if pc is None: aviso(f"{tr.name}: pestana compartida sin pared"); continue
            pc["slots"].append(slot_poly(seg, J3, wf)); continue
        pc, seg = seg_of(tr, tb["rec"])
        if pc is None: continue
        s_c = s_of(seg, J3)
        if tb["kind"] == "closed":
            pc["slots"].append(slot_poly(seg, J3, wf)); continue
        f2 = norm2(Vector((seg["L"], seg["C1"].z - seg["C0"].z)))
        nf, nw = wf["nf"], wf["nw"]; dz_out = -T * nf.dot(nw) / nf.z
        pc["notches"].append(dict(J=Vector((s_c, J3.z)), f=f2, hw=W_TAB / 2 + C_SLOT, top=C_SLOT + max(0.0, dz_out) * f2.x))
        if tb["kind"] != "open": continue
        zr = J3.z + RIV_PARED
        if zr + R_HOLE + 3.0 > z_at(pc["top"], s_c):
            aviso(f"{tr.name}/{pc['name']}: pared baja en s={s_c:.0f}, escuadra sin lugar"); tb["kind"] = "nobracket"; continue
        e3, u3 = wf["e3"], wf["u3"]
        wdn = (Vector((0, 0, -1)) - e3 * (-e3.z)).normalized()
        ang = math.degrees(math.acos(max(-1, min(1, u3.dot(wdn)))))
        Jb = J3 - Vector((0, 0, T / nf.z)); Jbo = Jb + nw * T + Vector((0, 0, dz_out))
        CLIPS.append(dict(tray=tr.name, pieza=pc["name"], pc=pc, s=s_c, z_rem=zr, hole_piso=J3 - u3 * RIV_PISO, g=tb["g"],
                          ang=ang, Jbo=Jbo, e3=e3, u3=u3, nf=nf, nw=nw, wdn=wdn, tab=tb))

# remaches pasantes entre una lateral superior y la central (pared en rendija)
THRU = []
for tr in TR.values():
  for Ow in [TR[o] for o in owners_of(tr.name) if o in TR]:
    for pc in tr.pieces:
        for seg in pc["segs"]:
            r = seg["rec"]
            if not r.get("gapwall") or seg["L"] < 20: continue
            best = None
            for k in range(4, 17):
                p = seg["L"] * k / 20; X = v2(seg["C0"]) + seg["d"] * p
                fr = free_at(tr, r, X)
                if not fr or fr[1] != Ow.name or not (0.3 <= fr[0] <= GAP_WALL): continue
                Q = fr[2] + seg["n"] * T                       # cara interior de la pared vecina
                opc, oseg = seg_near(Ow, Q)
                # altura del remache: de 6 mm bajo el borde hacia abajo (min. 6 mm sobre ambos pisos), la de mas luz al huevo
                z_hi = min(seg_top(tr, seg, X, p), z_at(opc["top"], s_of(oseg, Q))) - 6.0
                zfN = ztop(tr, r["g"], X); zfO = ztop(Ow, grp_at(Ow, Q), Q); opt = None; z = None
                for j in range(40):
                    zc = z_hi - 0.5 * j; hN = zc - zfN; hO = zc - zfO
                    if hN < 6.0 or hO < 6.0: break
                    cN, cO = egg_clear(hN), egg_clear(hO)
                    o_ = max(((min(cN - 1.2, cO - 3.5), "cabeza en la lateral, cola en la central"),
                              (min(cO - 1.2, cN - 3.5), "cabeza en la central, cola en la lateral")))
                    if opt is None or o_[0] > opt[0] + 1e-6: opt = o_; z = zc
                if opt is None: continue
                sN, sO = s_of(seg, X), s_of(oseg, Q)
                if any(abs(sN - n_["J"].x) < W_TAB / 2 + 4 for n_ in pc["notches"]): continue
                if any(min(q.x for q in sl) - 4 < sO < max(q.x for q in sl) + 4 for sl in opc["slots"]): continue
                if best is None or opt[0] > best[0]:
                    best = (opt[0], dict(tray=tr.name, pc=pc, s=sN, opc=opc, os=sO, z=z, gap=fr[0], lado=opt[1], luz=opt[0], X=X, Q=Q))
            if best: THRU.append(best[1])
            else: aviso(f"{tr.name}/{pc['name']}: tramo en rendija sin remache pasante")
for th in THRU:
    # PVC: si la cabeza del tornillo no tiene luz con el huevo, el separador se pega (sin agujeros ni tornillo)
    th["pegado"] = PVC and th["luz"] < 0.5
    if th["pegado"]: continue
    th["pc"]["holes"].append(circ(Vector((th["s"], th["z"])))); th["opc"]["holes"].append(circ(Vector((th["os"], th["z"]))))

# ------------------------------------------------------------------ contornos de las paredes
for tr in TR.values():
    for pc in tr.pieces: apoyar_sobre_pisos(tr, pc)          # pasada final (los recortes de extremos rehacen el perfil)
for tr in TR.values():
    for pc in tr.pieces:
        bot = list(pc["bot"])
        for m in sorted(pc["notches"], key=lambda m: m["J"].x):
            J, f2, hw, top = m["J"], m["f"], m["hw"], m["top"]; pp = Vector((-f2.y, f2.x))
            def side(sg, bot=bot):
                lo, hi = -40.0, top
                for _ in range(60):
                    mid = (lo + hi) / 2; P = J + f2 * (sg * hw) + pp * mid
                    if P.y - z_at(bot, P.x) > 0: hi = mid
                    else: lo = mid
                return J + f2 * (sg * hw) + pp * hi
            A, D = side(-1), side(1); Bp, Cp = J - f2 * hw + pp * top, J + f2 * hw + pp * top
            x0, x1 = min(A.x, Bp.x), max(Cp.x, D.x)
            bot = [q for q in bot if q.x < x0 - 1e-6] + [A, Bp, Cp, D] + [q for q in bot if q.x > x1 + 1e-6]
        pc["outline"] = ccw(list(pc["top"]) + list(reversed(bot)))
        if pc["notches"]: pc["outline"] = dogbone(pc["outline"], hole=False, min_turn=45.0)
        pc["bend_s"] = [s["S"] + s["flat"] for s in pc["segs"][:-1]]
        pc["zmin"] = min(p.y for p in pc["outline"])
        for sl in pc["slots"]:
            if min(q.y for q in sl) < z_at(pc["bot"], sum(q.x for q in sl) / len(sl)) + 0.8:
                aviso(f"{tr.name}/{pc['name']}: ranura cerrada demasiado cerca del borde inferior")

# ------------------------------------------------------------------ solidos 3D
def dedup(lp):
    out = []
    for p in lp:
        if not out or (p - out[-1]).length > 1e-5: out.append(p)
    while len(out) > 1 and (out[0] - out[-1]).length <= 1e-5: out.pop()
    return out
def slab(bm, outer, holes, to3, off):
    loops = [dedup(lp) for lp in [outer] + holes]
    loops = [lp for lp in loops if len(lp) >= 3]
    if not loops: return
    flat = [p for lp in loops for p in lp]
    tris = tessellate_polygon([[Vector((p.x, p.y, 0)) for p in lp] for lp in loops])
    vi = [bm.verts.new(to3(p)) for p in flat]; vo = [bm.verts.new(to3(p) + off) for p in flat]
    for a, b, c in tris:
        for vv, rev in ((vi, False), (vo, True)):
            try: bm.faces.new((vv[a], vv[c], vv[b]) if rev else (vv[a], vv[b], vv[c]))
            except ValueError: pass
    k = 0
    for lp in loops:
        n = len(lp)
        for i in range(n):
            a, b = k + i, k + (i + 1) % n
            try: bm.faces.new((vi[a], vi[b], vo[b], vo[a]))
            except ValueError: pass
        k += n
def box(bm, o, A, B, C, enc=0.0):
    if enc:   # caja encogida enc mm por cara (para probar choques sin contar el contacto)
        o = o + (A.normalized() + B.normalized() + C.normalized()) * enc
        A, B, C = A - A.normalized() * 2 * enc, B - B.normalized() * 2 * enc, C - C.normalized() * 2 * enc
    P = [o + A * i + B * j + C * k for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    vs = [bm.verts.new(p) for p in P]
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in q])
def clip_box(bm, c, enc=0.0):
    e3, u3, nf, nw, wdn, Jbo = c["e3"], c["u3"], c["nf"], c["nw"], c["wdn"], c["Jbo"]
    box(bm, Jbo - e3 * (W_TAB / 2) + u3 * (CLIP_T + 0.1) - nf * 0.1, e3 * W_TAB, -u3 * CLIP_H, -nf * CLIP_T, enc)
    box(bm, Jbo - e3 * (W_TAB / 2) + nw * 0.1 - wdn * 0.1, e3 * W_TAB, -wdn * (CLIP_V - CLIP_T - 0.2), nw * CLIP_T, enc)

def dedup_keep(lp): return lp
def floor_bm(tr, with_holes):
    bm = bmesh.new(); holes = [v2(c["hole_piso"]) for c in CLIPS if c["tray"] == tr.name] if with_holes else []
    for g, poly in tr.regions:
        hs = [circ(h) for h in holes if inside2(h, poly)]
        slab(bm, poly, hs, lambda q, g=g: lift(tr, q, g), -tr.G[g]["n"] * T)
    return bm
def wall_bm(pc, with_holes):
    bm = bmesh.new()
    for s in pc["segs"]:
        lo, hi = s["S"], s["S"] + s["flat"]
        part = clip_strip(list(pc["outline"]), lo, hi, 0)
        hs = [h for h in pc["slots"] + (pc["holes"] if with_holes else []) if lo < sum(q.x for q in h) / len(h) < hi]
        def to3(q, s=s):
            P = v2(s["C0"]) + s["d"] * (q.x - s["S"] - s["a0"]); return Vector((P.x, P.y, q.y))
        if len(part) >= 3: slab(bm, part, hs, to3, Vector((s["n"].x, s["n"].y, 0)) * T)
    return bm
def wedge_bm(tr, w):
    bm = bmesh.new(); r = w["rec"]; zt = min(r["ta"], r["tb"])
    base = list(w.get("poly") or [w["W0"], w["Sc"], w["S"]])
    if area2(base) < 0: base.reverse()
    lo = [bm.verts.new(P3(tr, p)) for p in base]; hi = [bm.verts.new(Vector((p.x, p.y, zt))) for p in base]
    bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    n_ = len(base)
    for i in range(n_): bm.faces.new((lo[i], lo[(i + 1) % n_], hi[(i + 1) % n_], hi[i]))
    return bm
def bvh_of(bm): return BVHTree.FromBMesh(bm)

# filtro: escuadras que chocan con algo (otras bandejas, bastidor) se quitan
solid_bvh = []
for tr in TR.values():
    solid_bvh.append((tr.name + "/Piso", bvh_of(floor_bm(tr, False))))
    for pc in tr.pieces: solid_bvh.append((tr.name + "/" + pc["name"], bvh_of(wall_bm(pc, False))))
scene_bvh = []
for ob in bpy.context.view_layer.objects:
    if ob.type != 'MESH' or not ob.visible_get() or ob.name.startswith(IGNORAR): continue
    oe = ob.evaluated_get(_dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(Matrix.Scale(1000.0, 4) @ ob.matrix_world); scene_bvh.append((ob.name, BVHTree.FromBMesh(b))); b.free()
keep = []
for c in CLIPS:
    b = bmesh.new(); clip_box(b, c, 0.15); t = bvh_of(b); b.free()       # 0.15 mm: el contacto con la pared no cuenta
    hit = next((nm for nm, bv in solid_bvh + scene_bvh if t.overlap(bv)), None)
    if hit: aviso(f"{c['tray']}/{c['pieza']}: escuadra en s={c['s']:.0f} choca con {hit}; queda solo la pestana"); c["tab"]["kind"] = "nobracket"
    else: keep.append(c)
CLIPS = keep
for c in CLIPS: c["pc"]["holes"].append(circ(Vector((c["s"], c["z_rem"]))))

for ob in list(bpy.data.objects):
    if ob.name.startswith(("ACM_", "PVC_", "PETG_Cuna", "PETG_Escuadras")): bpy.data.objects.remove(ob, do_unlink=True)
for cl in list(bpy.data.collections):
    if cl.name.startswith(("Alucobond_", "PVC_")) and not cl.objects: bpy.data.collections.remove(cl)
if PVC: mat = bpy.data.materials.get("PVC_Blanco") or bpy.data.materials.new("PVC_Blanco"); mat.diffuse_color = (0.92, 0.92, 0.9, 1.0)
else: mat = bpy.data.materials.get("Alucobond_Gris") or bpy.data.materials.new("Alucobond_Gris"); mat.diffuse_color = (0.78, 0.80, 0.82, 1.0)
mat_h = bpy.data.materials.get("Aluminio_Escuadras") or bpy.data.materials.new("Aluminio_Escuadras"); mat_h.diffuse_color = (0.55, 0.58, 0.62, 1.0)
mat_p = bpy.data.materials.get("PETG_Naranja") or bpy.data.materials.new("PETG_Naranja"); mat_p.diffuse_color = (0.95, 0.45, 0.1, 1.0)
def make_obj(coll, name, bm, m):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.scale(bm, vec=(0.001, 0.001, 0.001), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); me.materials.append(m); return ob
OBJS = {}
for tr in TR.values():
    cn = CPFX + tr.name
    coll = bpy.data.collections.get(cn) or bpy.data.collections.new(cn)
    if coll.name not in [c.name for c in bpy.context.scene.collection.children]: bpy.context.scene.collection.children.link(coll)
    objs = {"Piso": make_obj(coll, f"{PFX}{tr.name}_Piso", floor_bm(tr, True), mat)}
    for pc in tr.pieces: objs[pc["name"]] = make_obj(coll, f"{PFX}{tr.name}_{pc['name']}", wall_bm(pc, True), mat)
    cl = [c for c in CLIPS if c["tray"] == tr.name]
    if cl:
        b = bmesh.new()
        for c in cl: clip_box(b, c)
        objs["Escuadras"] = make_obj(coll, f"PETG_Escuadras_{tr.name}" if PVC else f"ACM_{tr.name}_Escuadras", b, mat_p if PVC else mat_h)
    for k, w in enumerate(tr.wedges): objs[f"Cuna{k+1}"] = make_obj(coll, f"PETG_Cuna_{tr.name}_{k+1}", wedge_bm(tr, w), mat_p)
    OBJS[tr.name] = objs

# ------------------------------------------------------------------ DXF, SVG, herrajes
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), (LIN, 5), ("TEXTO_NO_CORTAR", 3)]
def dxf(path, polys, lines_, texts):
    o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
    for nm, col in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(col), "6", "CONTINUOUS"]
    o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    f = lambda v: "%.4f" % v
    for lay, pts in polys:
        o += ["0", "POLYLINE", "8", lay, "66", "1", "70", "1", "10", "0", "20", "0", "30", "0"]
        for p in pts: o += ["0", "VERTEX", "8", lay, "10", f(p.x), "20", f(p.y), "30", "0"]
        o += ["0", "SEQEND", "8", lay]
    for lay, a, b in lines_: o += ["0", "LINE", "8", lay, "10", f(a.x), "20", f(a.y), "30", "0", "11", f(b.x), "21", f(b.y), "31", "0"]
    for lay, p, h, txt in texts: o += ["0", "TEXT", "8", lay, "10", f(p.x), "20", f(p.y), "30", "0", "40", f(h), "1", txt]
    o += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o) + "\n")
COL = {"CORTE_EXTERIOR": "#111", "CORTE_INTERIOR": "#d22", "RANURA_V": "#1565c0", "DOBLEZ": "#1565c0", "TEXTO_NO_CORTAR": "#2e7d32"}
def svg_write(path, drawings):
    svg = []; yoff = 0.0; Wmax = 300.0
    for nm, dr in drawings.items():
        pts = [p for _, ps in dr["polys"] for p in ps]
        x1 = max(p.x for p in pts); y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
        ytxt = max([y1] + [p.y for _, p, _, _ in dr["texts"]]) + 6
        H = ytxt - min([y0] + [p.y for _, a, b in dr["lines"] for p in (a, b)]) + 10; base = yoff + ytxt
        Y = lambda y: base - y
        for lay, ps in dr["polys"]:
            svg.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="0.4"/>' % (
                " ".join("%.2f,%.2f" % (p.x + 10, Y(p.y)) for p in ps), "#e9eef3" if lay == "CORTE_EXTERIOR" else "#fff", COL[lay]))
        for lay, a, b in dr["lines"]:
            svg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.5" stroke-dasharray="%s"/>' % (
                a.x + 10, Y(a.y), b.x + 10, Y(b.y), COL[lay], "3,2" if lay in ("RANURA_V", "DOBLEZ") else "none"))
        for lay, p, h, t_ in dr["texts"]:
            svg.append('<text x="%.2f" y="%.2f" font-size="%.1f" font-family="sans-serif" fill="%s">%s</text>' % (p.x + 10, Y(p.y), h, COL[lay], t_))
        yoff += H + 12; Wmax = max(Wmax, x1 + 20)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" width="%.0fmm" height="%.0fmm"><rect width="100%%" height="100%%" fill="#fff"/>%s</svg>'
                 % (Wmax, yoff, Wmax, yoff, "".join(svg)))

def chord(poly, a, b):
    d = b - a; ts = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]; e = q - p; den = cross2(d, e)
        if abs(den) < 1e-12: continue
        t = cross2(p - a, e) / den; u = cross2(p - a, d) / den
        if 0 <= u <= 1: ts.append(t)
    lo = max([t for t in ts if t <= 0.5] or [0.0]); hi = min([t for t in ts if t >= 0.5] or [1.0])
    return a + d * lo, a + d * hi

for f_ in os.listdir(OUT):
    if f_.startswith(tuple(TRAYS)) and f_.endswith((".dxf", ".svg", "_herrajes.txt")): os.remove(os.path.join(OUT, f_))
rep["piezas"] = {}
for tr in TR.values():
    drawings = {}
    ox, oy = max(p.x for p in tr.floor2d), -min(p.y for p in tr.floor2d)
    sh = lambda p, ox=ox, oy=oy: Vector((-p.x + ox, p.y + oy))     # vista desde abajo (cara B arriba en la CNC)
    polys = [("CORTE_EXTERIOR", [sh(p) for p in tr.floor2d])]
    for c in CLIPS:
        if c["tray"] == tr.name: polys.append(("CORTE_INTERIOR", [sh(p) for p in circ(to2d(tr.tf[c["g"]], c["hole_piso"]))]))
    lns = []; txs = []
    for f in tr.folds:
        a2, b2 = chord(tr.floor2d, to2d(tr.tf[f["g1"]], f["A"]), to2d(tr.tf[f["g1"]], f["B"]))
        lns.append((LIN, sh(a2), sh(b2)))
        if PVC:   # normal: la cara B (abajo) queda concava; invertido: la cara A (huevos) queda concava
            txt_ = "DOBLAR %.1f deg - concava cara %s" % (f["ang"], "B (abajo)" if f["tipo"] == "normal" else "A (huevos)")
        else: txt_ = "%.1f deg %s" % (f["ang"], "V CIERRA" if f["tipo"] == "normal" else "INVERTIDO: V ABRE")
        txs.append(("TEXTO_NO_CORTAR", sh((a2 + b2) / 2) + Vector((2, 1.5)), 2.5, txt_))
    xs = [p.x for _, ps in polys for p in ps]; ys = [p.y for _, ps in polys for p in ps]
    if PVC:
        txs += [("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 8)), 4.0, f"PISO {tr.name.upper()} - PVC {T:g} mm - x1"),
                ("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 15)), 3.0, "VISTA DESDE LA CARA B (abajo). Cara A = donde ruedan los huevos"),
                ("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 21)), 3.0, "Punteado = DOBLAR con calor (no cortar). Agujeros D3.4 = tornillo M3")]
    else:
        txs += [("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 8)), 4.0, f"PISO {tr.name.upper()} - ACM {T:g} mm - x1"),
                ("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 15)), 3.0, "CARA ARRIBA EN CNC: B (inferior). Ranuras V por esta cara. Cara A = donde ruedan los huevos"),
                ("TEXTO_NO_CORTAR", Vector((min(xs), max(ys) + 21)), 3.0, "Ranura V: dejar %.1f mm de material en el fondo. Agujeros D4.1 = remaches ciegos D4" % RESTO)]
    lns.append(("TEXTO_NO_CORTAR", Vector((min(xs), min(ys) - 10)), Vector((min(xs) + 100, min(ys) - 10))))
    txs.append(("TEXTO_NO_CORTAR", Vector((min(xs), min(ys) - 16)), 3.0, "Referencia 100 mm"))
    drawings["Piso"] = dict(polys=polys, lines=lns, texts=txs)
    for pc in tr.pieces:
        def trf(p, pc=pc):
            return Vector((pc["S"] - p.x if pc["mirror"] else p.x, p.y - pc["zmin"]))
        polys = ([("CORTE_EXTERIOR", [trf(p) for p in pc["outline"]])] + [("CORTE_INTERIOR", [trf(p) for p in sl]) for sl in pc["slots"]]
                 + [("CORTE_INTERIOR", [trf(p) for p in h]) for h in pc["holes"]])
        ln = []; tx = []; zt = max(p.y for p in pc["outline"])
        for k, sb in enumerate(pc["bend_s"]):
            a = trf(Vector((sb, z_at(pc["top"], sb)))); b = trf(Vector((sb, z_at(pc["bot"], sb))))
            ln.append((LIN, b, a))
            cn = pc["corners"][k]
            inv = (pc["cara"] == "A") != cn["concava"] and cn["ang"] >= 0.5
            if PVC:
                cc = pc["cara"] if not inv else ("B" if pc["cara"] == "A" else "A")
                tx.append(("TEXTO_NO_CORTAR", a + Vector((1.0, 2.0)), 2.5, "%.1f deg concava %s" % (cn["ang"], "A (int)" if cc == "A" else "B (ext)")))
            else: tx.append(("TEXTO_NO_CORTAR", a + Vector((1.0, 2.0)), 2.5, "%.1f%s" % (cn["ang"], " INV" if inv else "")))
        lado = "A (interior)" if pc["cara"] == "A" else "B (exterior)"
        if PVC:
            tx += [("TEXTO_NO_CORTAR", Vector((0, zt - pc["zmin"] + 12)), 4.0, f"PARED {tr.name.upper()} {pc['name'].upper()} - PVC {T:g} mm - x1"),
                   ("TEXTO_NO_CORTAR", Vector((0, zt - pc["zmin"] + 6)), 3.0, "VISTA DESDE LA CARA %s. Punteado = doblar con calor" % lado)]
        else:
            tx += [("TEXTO_NO_CORTAR", Vector((0, zt - pc["zmin"] + 12)), 4.0, f"PARED {tr.name.upper()} {pc['name'].upper()} - ACM {T:g} mm - x1"),
                   ("TEXTO_NO_CORTAR", Vector((0, zt - pc["zmin"] + 6)), 3.0, "CARA ARRIBA EN CNC: %s. Ranuras V por esta cara" % lado)]
        drawings[pc["name"]] = dict(polys=polys, lines=ln, texts=tx)
    for nm, dr in drawings.items(): dxf(os.path.join(OUT, f"{tr.name}_{TAG}_{nm}.dxf"), dr["polys"], dr["lines"], dr["texts"])
    svg_write(os.path.join(OUT, f"{tr.name}_{TAG}_vista_previa.svg"), drawings)
    rep["piezas"][tr.name] = {nm: [round(max(p.x for _, ps in dr["polys"] for p in ps) - min(p.x for _, ps in dr["polys"] for p in ps), 1),
                                   round(max(p.y for _, ps in dr["polys"] for p in ps) - min(p.y for _, ps in dr["polys"] for p in ps), 1)]
                              for nm, dr in drawings.items()}
    cl = [c for c in CLIPS if c["tray"] == tr.name]; th = [t for t in THRU if t["tray"] == tr.name]
    tabs = Counter(t["kind"] for t in tr.tabs)
    with open(os.path.join(OUT, f"{tr.name}_{TAG}_herrajes.txt"), "w", encoding="utf-8") as fh:
        W = fh.write
        W(f"{tr.name} - {'PVC' if PVC else 'ALUCOBOND'} {T:g} mm - HERRAJES Y ARMADO\n\n")
        W(f"Piezas: Piso + {', '.join(pc['name'] for pc in tr.pieces)}\n")
        W(f"Pestanas del piso: {len(tr.tabs)} (muesca abierta + escuadra: {tabs['open']}, muesca abierta sin escuadra: {tabs['nobracket']},\n"
          f"  ranura cerrada en pared propia: {tabs['closed']}, ranura cerrada en pared de otra bandeja: {tabs['shared']})\n\n")
        if cl and PVC:
            W(f"Escuadras impresas en PETG {CLIP_T:g} mm por fuera: {len(cl)} ({W_TAB:.0f} mm de ancho, ala bajo el piso {CLIP_H:.0f}, ala exterior {CLIP_V:.0f})\n")
            for a, n in sorted(Counter(round(c["ang"]) for c in cl).items()): W(f"    {a} grados: {n}  -> stl/bandejas_pvc/Escuadra_{a}deg.stl\n")
            W(f"  Tornillos M3 x 10 cabeza boton o plana (cabeza por DENTRO de la bandeja) + arandela + tuerca M3 por fuera: {2 * len(cl)}\n")
        elif cl:
            W(f"Escuadras de aluminio 2 mm por fuera: {len(cl)} ({W_TAB:.0f} mm de ancho, ala bajo el piso {CLIP_H:.0f}, ala exterior {CLIP_V:.0f})\n")
            for a, n in sorted(Counter(round(c["ang"]) for c in cl).items()): W(f"    {a} grados: {n}\n")
            W(f"  Remaches ciegos D4 cabeza redonda 4x10: {2 * len(cl)} (piso desde arriba, pared desde adentro)\n")
            for c in cl: W(f"    {c['pieza']:<12} s={c['s']:7.1f} mm  {c['ang']:5.1f} grados\n")
        if th:
            W(f"\n{'Tornillos' if PVC else 'Remaches'} pasantes con separador (pared en rendija con la bandeja central): {len(th)}\n")
            for t in th:
                fij = (("SIN tornillo: bloque PETG 12x12 pegado con epoxi entre las dos paredes (no hay luz para una cabeza)" if t["pegado"]
                        else f"tornillo M3 x {math.ceil(2 * T + t['gap'] + 4):.0f} + tuerca") if PVC else f"remache D4 agarre {2 * T + t['gap']:.1f} mm")
                W(f"    {t['pc']['name']} s={t['s']:.1f} / central {t['opc']['name']} s={t['os']:.1f}, z={t['z']:.1f}: separador PETG "
                  f"D8x{t['gap']:.1f} mm, {fij}, {t['lado']} (luz al huevo {t['luz']:.1f} mm)\n")
        if tr.wedges:
            W(f"\nCunas impresas en PETG (transicion pared compartida -> pared propia): {len(tr.wedges)}\n")
            for k, w in enumerate(tr.wedges):
                W(f"    Cuna {k+1}: triangulo {w['Lw']:.1f} x {T:.0f} mm, angulo {w['ang']:.1f} grados, alto hasta el borde de la pared; pegar sobre el piso\n")
        own = [TR[n] for n in partners_of(tr.name) if n in TR]
        if own: W(f"\nParedes compartidas con: {', '.join(t.name for t in own)}. Esas paredes bajan {M_SLOT} mm bajo el piso mas bajo;\n"
                  "  las pestanas de ambos pisos entran en ranuras cerradas (sin escuadra). Sellador en la union.\n")
        if owners_of(tr.name): W(f"\nComparte pared con {', '.join(owners_of(tr.name))}: el piso llega hasta la cara exterior de esa pared y sus pestanas\n"
                               "  entran en ranuras cerradas de esa pared.\n")
        if PVC:
            W("\nOrden de armado (PVC):\n"
              "  1) Pegar la plantilla 1:1 (plantillas_pvc) sobre la lamina, cortar con cuter/sierra. Agujeros D3.4 con broca.\n"
              "     Ranuras cerradas: 2 agujeros D2.5 en los extremos y cortar entre ellos con cuter. Esquinas interiores: agujero D3.\n"
              "  2) Doblar el piso con pistola de calor sobre cada linea punteada, al angulo indicado y con la cara concava indicada\n"
              "     (conviene una plantilla de carton con el angulo). Mismo procedimiento con las esquinas de las paredes.\n"
              "  3) Montar las paredes con las pestanas del piso en sus muescas/ranuras.\n"
              "  4) Escuadras PETG por fuera: tornillo M3 con la cabeza por dentro (lado de los huevos), arandela y tuerca por fuera.\n"
              "  5) Opcional: sellar juntas con cemento para PVC.\n"
              "  Tolerancia del desarrollo con doblez a calor: +-1 mm por esquina de 90 grados.\n")
        else:
            W("\nOrden de armado: 1) plegar el piso (adhesivo en las ranuras V); 2) plegar las paredes; 3) montar las paredes con las\n"
              "  pestanas en sus muescas/ranuras; 4) sellador en las juntas entre paredes; 5) escuadras por fuera: presentar,\n"
              "  taladrar a traves de los agujeros y remachar.\n")

# ------------------------------------------------------------------ piezas impresas (PVC): escuadras por angulo, cunas, separadores
def stl_bm(path, bm):
    """exporta un bmesh en mm como STL en mm"""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bmesh.ops.scale(bm, vec=(0.001, 0.001, 0.001), verts=bm.verts)
    me = bpy.data.meshes.new("tmp_stl"); bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("tmp_stl", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1000.0)
    bpy.data.objects.remove(ob, do_unlink=True); bpy.data.meshes.remove(me)
def bool_dif(bm, cortes):
    """resta cilindros (bmesh) a bm; devuelve un bmesh nuevo"""
    me = bpy.data.meshes.new("tmp_a"); bm.to_mesh(me); bm.free(); a = bpy.data.objects.new("tmp_a", me); bpy.context.scene.collection.objects.link(a)
    me2 = bpy.data.meshes.new("tmp_b"); cortes.to_mesh(me2); cortes.free(); b = bpy.data.objects.new("tmp_b", me2); bpy.context.scene.collection.objects.link(b)
    md = a.modifiers.new("d", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = b; md.solver = 'EXACT'
    with bpy.context.temp_override(object=a, active_object=a): bpy.ops.object.modifier_apply(modifier=md.name)
    out = bmesh.new(); out.from_mesh(a.data)
    bpy.data.objects.remove(a, do_unlink=True); bpy.data.objects.remove(b, do_unlink=True); bpy.data.meshes.remove(me); bpy.data.meshes.remove(me2)
    return out
def escuadra_bm(alfa):
    """escuadra en L con angulo interior alfa (grados): perfil en XY (ala del piso sobre +x), ancho W_TAB en Z.
    Se imprime acostada sobre el perfil: las capas quedan en el plano en que trabaja la escuadra."""
    a = math.radians(alfa); w = Vector((math.cos(a), math.sin(a))); nw = Vector((-math.sin(a), math.cos(a)))
    t = CLIP_T; s_ = -t * (1 + math.cos(a)) / max(math.sin(a), 1e-6)
    pts = [Vector((0, 0)), w * CLIP_V, nw * t + w * CLIP_V, nw * t + w * s_, Vector((CLIP_H, -t)), Vector((CLIP_H, 0))]
    if area2(pts) < 0: pts.reverse()
    bm = bmesh.new(); lo = [bm.verts.new((p.x, p.y, 0)) for p in pts]; hi = [bm.verts.new((p.x, p.y, W_TAB)) for p in pts]
    bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    for i in range(len(pts)): bm.faces.new((lo[i], lo[(i + 1) % len(pts)], hi[(i + 1) % len(pts)], hi[i]))
    cb = bmesh.new()
    for c_, d_ in ((Vector((T + RIV_PISO, 0)), Vector((0, -1))), (w * (T + RIV_PARED), -nw)):   # agujeros D4.4 (remache 3 mm; impreso sale chico) en el centro del ancho
        g_ = bmesh.ops.create_cone(cb, cap_ends=True, segments=24, radius1=2.2, radius2=2.2, depth=4 * t)
        bmesh.ops.rotate(cb, verts=g_['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector((d_.x, d_.y, 0))).to_matrix())
        bmesh.ops.translate(cb, verts=g_['verts'], vec=(c_.x + d_.x * t / 2, c_.y + d_.y * t / 2, W_TAB / 2))
    return bool_dif(bm, cb)
if PVC and "save" in argv:
    os.makedirs(STL_OUT, exist_ok=True)
    for f_ in os.listdir(STL_OUT):
        if f_.endswith(".stl"): os.remove(os.path.join(STL_OUT, f_))
    angs = Counter(round(c["ang"]) for c in CLIPS)
    for a, n in angs.items(): stl_bm(os.path.join(STL_OUT, f"Escuadra_{a}deg.stl"), escuadra_bm(a))
    for tr in TR.values():
        for k, w in enumerate(tr.wedges):
            b = wedge_bm(tr, w); c0 = sum((v.co for v in b.verts), Vector()) / len(b.verts)
            bmesh.ops.translate(b, verts=b.verts, vec=-c0); stl_bm(os.path.join(STL_OUT, f"Cuna_{tr.name}_{k+1}.stl"), b)
    for t in THRU:
        if t["pegado"]:          # bloque para pegar (un poco menos que la rendija para que entre con el adhesivo)
            b = bmesh.new(); g_ = bmesh.ops.create_cube(b, size=1.0); bmesh.ops.scale(b, verts=g_['verts'], vec=(12.0, 12.0, max(t["gap"] - 0.3, 0.6)))
            stl_bm(os.path.join(STL_OUT, f"Separador_pegado_{t['tray']}_{t['gap'] - 0.3:.1f}mm.stl"), b); continue
        b = bmesh.new(); bmesh.ops.create_cone(b, cap_ends=True, segments=32, radius1=4.0, radius2=4.0, depth=t["gap"])
        cb = bmesh.new(); bmesh.ops.create_cone(cb, cap_ends=True, segments=24, radius1=2.2, radius2=2.2, depth=t["gap"] + 2)
        stl_bm(os.path.join(STL_OUT, f"Separador_{t['tray']}_{t['gap']:.1f}mm.stl"), bool_dif(b, cb))
    rep["stl_pvc"] = sorted(os.listdir(STL_OUT)); rep["escuadras_por_angulo"] = dict(sorted(angs.items()))

# ------------------------------------------------------------------ revision
def bvh_ob(o):
    oe = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
from mathutils.geometry import intersect_point_tri
SHRINK = 0.3     # mm: los solidos se encogen antes de buscar choques (ignora roces de decimas en esquinas)
def tris_of(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(Matrix.Scale(1000.0, 4) @ o.matrix_world)
    b.normal_update()
    for v in b.verts: v.co -= v.normal * SHRINK
    bmesh.ops.triangulate(b, faces=b.faces); b.faces.ensure_lookup_table()
    return BVHTree.FromBMesh(b), [[v.co.copy() for v in f.verts] for f in b.faces]
def xpoints(A, B):
    (ba, ta), (bb, tb) = A, B; pts = []
    for i, j in ba.overlap(bb):
        for T1, T2 in ((ta[i], tb[j]), (tb[j], ta[i])):
            n = (T2[1] - T2[0]).cross(T2[2] - T2[0])
            if n.length < 1e-12: continue
            n.normalize()
            for k in range(3):
                p, q = T1[k], T1[(k + 1) % 3]; dp, dq = (p - T2[0]).dot(n), (q - T2[0]).dot(n)
                if dp * dq < 0 and min(abs(dp), abs(dq)) > 1e-4:
                    X = p + (q - p) * (dp / (dp - dq))
                    if intersect_point_tri(X, *T2): pts.append(X)
    return pts
allo = [(tn, k, o) for tn, d in OBJS.items() for k, o in d.items()]
TT = {o.name: tris_of(o) for _, _, o in allo}
ch = []
for i in range(len(allo)):
    for j in range(i + 1, len(allo)):
        a, b = allo[i][2], allo[j][2]; P = xpoints(TT[a.name], TT[b.name])
        if P:
            lo = [round(min(p[k] for p in P)) for k in range(3)]; hi = [round(max(p[k] for p in P)) for k in range(3)]
            ch.append(f"{a.name} x {b.name}: {len(P)} pts en x{lo[0]}..{hi[0]} y{lo[1]}..{hi[1]} z{lo[2]}..{hi[2]}")
rep["choques_entre_piezas"] = ch
BV = {o.name: bvh_ob(o) for _, _, o in allo}
others = [o for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.visible_get() and not o.name.startswith(IGNORAR)]
OB_BV = {x.name: bvh_ob(x) for x in others}
rep["donde_bastidor"] = []
for _, _, o in allo:
    for x in ("Bastidor_Largueros_2020.003",):
        if x in OB_BV and BV[o.name].overlap(OB_BV[x]) and o.name.startswith(PFX + "BandejaCentral"):
            P = xpoints(TT[o.name], tris_of(O[x]))
            if P: rep["donde_bastidor"].append(f"{o.name}: x{min(p.x for p in P):.0f}..{max(p.x for p in P):.0f} y{min(p.y for p in P):.0f}..{max(p.y for p in P):.0f} z{min(p.z for p in P):.0f}..{max(p.z for p in P):.0f}")
rep["choques_con_maquina"] = sorted({f"{o.name} x {x}" for _, _, o in allo for x, bv in OB_BV.items() if BV[o.name].overlap(bv)})
rep["choques_originales"] = sorted({f"{tn} x {x}" for tn in TR for x, bv in OB_BV.items() if bvh_ob(O[tn]).overlap(bv)})
cerca = {}
for a in TR.values():
    for b in TR.values():
        if a.name >= b.name or paired(a.name, b.name): continue
        for r in a.recs:
            if not r["wall"] or r["kind"] != "own": continue
            for k in range(11):
                X = v2(r["A"] + (r["B"] - r["A"]) * (k / 10)); gp = gap_at(X, r, b)
                if gp and gp[0] < GAP_SHARED:
                    zr = (r["ta"] + r["A"].z) / 2; q = gp[1]
                    if min(q["A"].z, q["B"].z) - 6 < max(r["ta"], r["tb"]) and min(r["A"].z, r["B"].z) - 6 < max(q["ta"], q["tb"]):
                        cerca.setdefault(f"{a.name}{r['vi']} - {b.name}{q['vi']}", []).append(round(gp[0], 1))
rep["paredes_muy_cerca"] = {k: [min(v), max(v)] for k, v in cerca.items()}
rep["escuadras"] = {tn: len([c for c in CLIPS if c["tray"] == tn]) for tn in TR}
rep["pestanas"] = {tn: dict(Counter(t["kind"] for t in tr.tabs)) for tn, tr in TR.items()}
rep["remaches_pasantes"] = [dict(tray=t["tray"], pieza=t["pc"]["name"], gap=round(t["gap"], 1), luz=round(t["luz"], 1), lado=t["lado"],
                                 pegado=t.get("pegado", False)) for t in THRU]
rep["cunas"] = {tn: [dict(Lw=round(w["Lw"], 1), ang=round(w["ang"], 1)) for w in tr.wedges] for tn, tr in TR.items() if tr.wedges}
rep["pliegues_piso"] = {tn: [[round(f["ang"], 1), f["tipo"]] for f in tr.folds] for tn, tr in TR.items()}
rep["paredes"] = {tn: {pc["name"]: dict(cara=pc["cara"], largo=round(pc["S"], 1), esquinas=[round(c["ang"], 1) for c in pc["corners"]],
                                        ranuras=len(pc["slots"]), muescas=len(pc["notches"]), agujeros=len(pc["holes"]))
                       for pc in tr.pieces} for tn, tr in TR.items()}
rep["muescas_bastidor"] = sorted(rep.get("muescas_bastidor", []))
rep["salida"] = OUT
if "save" in argv:
    for nm in TR: O[nm].hide_set(True)
    bpy.ops.wm.save_mainfile(); rep["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(rep))
