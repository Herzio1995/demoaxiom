"""
Ovum2_0: "Soporte principal2_0" en alucobond (ACM) de 4 mm para corte CNC, con esquineros de PETG.

Piezas
  1) Base_Respaldo (ACM 4, x1): placa base + respaldo, un pliegue de 90 grados con ranura V por la cara A (interior).
  2) Oreja (ACM 4, x2): planas, sin pliegues. Llevan el agujero del eje (Ø11.5) con ACM entero alrededor:
     el respaldo queda ENTRE las orejas, asi detras del agujero quedan 4.7 mm de ACM sano (no una ranura V).
  3) Esquinero PETG (x2): pie en la esquina inferior interior + columna en la esquina oreja-respaldo hasta z~150.
     Une base, respaldo y oreja con 5 tornillos M3 a insertos termicos, todos desde abajo o desde afuera
     (sin remaches: por fuera del lado derecho, sobre z 136.5, esta SoporteServoEmpujadorMediaLuna).
  4) Buje PETG con pestana (x2): en el agujero del eje, pestana por dentro.
  5) Soporte del servo de la media luna (reemplaza a SoporteServoEmpujadorMediaLuna, impreso), INTEGRADO en
     Base_Respaldo: el borde derecho de la base se pliega hacia arriba y forma la placa del servo (perpendicular a su
     eje). La ventana del servo no se tira: se corta en U y se pliega hacia adentro como BANDEJA bajo el cuerpo.
     Los dos pliegues nuevos tienen la ranura V por la misma cara A. El servo se atornilla por su brida (4 tornillos).

Reglas de espesor (el original era aluminio de 3 mm / 2.6 mm)
  - Caras interiores fijas: cara superior de la placa (z 104.36), cara delantera del respaldo (y -112.01) y caras
    interiores de las orejas (x -31.34 / 31.77). El material crece hacia abajo y hacia afuera.
  - Borde izquierdo de la placa: -34.04 -> -35.34 (= cara exterior de la oreja izquierda).
  - Detras de la oreja derecha la placa termina en y -112.01 (antes -114.56): el respaldo plegado ocupa ese lugar.

Uso:  dentro de Blender: exec(open(r"...\\acm4_soporte_principal_ovum2_0.py", encoding="utf-8").read())
      o  blender --background <archivo>.blend --python acm4_soporte_principal_ovum2_0.py [-- save]
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.geometry import tessellate_polygon
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
BASE_DIR = os.path.dirname(bpy.data.filepath)
OUT = os.path.join(BASE_DIR, "cnc", "alucobond")
STL = os.path.join(BASE_DIR, "stl", "SoportePrincipal_ACM4")
os.makedirs(OUT, exist_ok=True); os.makedirs(STL, exist_ok=True)
rep = {"avisos": []}

# ------------------------------------------------------------------ parametros (mm)
T = 4.0                       # espesor ACM
RESTO = 0.8                   # material en el fondo de la ranura V
D = T - RESTO                 # profundidad de la ranura (y medio ancho en la cara A)
R_TOOL = 1.6                  # fresa 1/8"
Z_TOP = 104.36                # cara superior de la placa (fija)
Z_BOT = Z_TOP - T             # 100.36
Y_IN = -112.01                # cara delantera del respaldo (fija)
Y_OUT = Y_IN - T              # -116.01
XL_IN, XR_IN = -31.34, 31.77  # caras interiores de las orejas (fijas)
XL_OUT, XR_OUT = XL_IN - T, XR_IN + T
Y_FRONT = -92.59              # borde delantero de las orejas
Z_EAR = 180.12                # alto de orejas y esquinas del respaldo
EJE = (-105.47, 167.2, 11.5)  # agujero del eje en las orejas (y, z, diametro) - igual que el original
R_M3 = 1.7                    # paso M3
R_RIV = 2.05                  # remache ciego D4
# esquinero PETG (medidas desde la esquina interior: a lo largo de la oreja->x', del respaldo->y', alto z')
EQ_X, EQ_Y, EQ_Z = 16.0, 16.0, 14.0
EQ_COL = (10.0, 11.0, 46.0)   # columna en la esquina oreja-respaldo (x', y', alto z'); y' <= 11 libra el soporte del pesador
EQ_HB = [(11.0, 11.0)]                # tornillos verticales (base), desde abajo: (x', y')
EQ_HR = [(5.0, 9.0), (5.0, 28.0)]     # tornillos por el respaldo, desde atras: (x', z'); z' 28 -> cabeza bajo z 136.5
EQ_HO = [(13.0, 5.0), (5.5, 18.0)]    # tornillos por la oreja, desde afuera: (y', z')
INS_D, INS_L = 4.0, 6.0       # agujero para inserto termico M3
# buje PETG
BUJE_OD, BUJE_FL_D, BUJE_FL_T, BUJE_ID = 11.4, 17.0, 1.5, 5.2
# soporte del servo de la media luna (placa + bandeja plegadas desde la base). El servo del modelo es una caja sin
# brida: medidas de un servo estandar tipo MG996R (AJUSTAR al servo real; agujeros de la brida = ranuras de +-SV_RAN)
SERVO = "SoporteGuiadorCuadradoImprimir.002"
SV_BRIDA = 14.5              # de la cara del eje del servo (tapa) a la cara de apoyo de la brida
SV_AG_L, SV_AG_W, SV_AG_D, SV_RAN = 49.5, 10.0, 4.3, 1.0   # agujeros de la brida: separacion largo/ancho, D, ranura +-
SV_HOLG = 0.6                # holgura de la ventana alrededor del cuerpo
SV_MARGEN = 3.0              # material de la placa por fuera de los agujeros
SV_APOYO = 0.3               # luz entre la bandeja y el cuerpo del servo
BAND_L = 15.2                # largo minimo de la bandeja (de la placa hacia la oreja); se alarga si la ventana lo pide
KERF = 3.4                   # corte alrededor de la bandeja (fresa 1/8" + juego)
YW_FRONT = -85.0             # borde delantero de la placa del servo (libra Soporte HuevoPesadorOriginall, y >= -81.1)
Y_BASE_STEP = -81.4          # desde aca hacia adelante la base vuelve a llegar a x 60.75 (alivio de 3.6 mm)

m = lambda v: v / 1000.0
def M(x, y, z): return Vector((m(x), m(y), m(z)))

# ------------------------------------------------------------------ geometria auxiliar
def circle(cx, cy, r, n=48): return [Vector((cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))) for k in range(n)]
def area2(p): return 0.5 * sum(p[i].x * p[(i + 1) % len(p)].y - p[(i + 1) % len(p)].x * p[i].y for i in range(len(p)))
def ccw(p): return p if area2(p) > 0 else list(reversed(p))
def dogbone_rect(x0, y0, x1, y1, r=R_TOOL, seg=10):
    """ventana rectangular con alivios en las 4 esquinas (para que entre una pieza de esquinas vivas)"""
    C = [Vector((x0, y0)), Vector((x1, y0)), Vector((x1, y1)), Vector((x0, y1))]     # antihorario
    out = []
    for i, c in enumerate(C):
        e_in = (c - C[i - 1]).normalized(); e_out = (C[(i + 1) % 4] - c).normalized()
        cen = c + (e_in - e_out) * (r / 2)              # circulo de radio r que pasa por la esquina, hacia afuera
        p1 = c - e_in * (0.366 * r); p2 = c + e_out * (0.366 * r)
        a1 = math.atan2(p1.y - cen.y, p1.x - cen.x); a2 = math.atan2(p2.y - cen.y, p2.x - cen.x)
        while a2 > a1: a2 -= 2 * math.pi                 # sentido horario: el arco pasa por afuera de la esquina
        out += [cen + Vector((math.cos(a1 + (a2 - a1) * k / seg), math.sin(a1 + (a2 - a1) * k / seg))) * r for k in range(seg + 1)]
    return ccw(out)

def prism(bm, outline, holes, z0, z1, to3):
    """extruye un poligono 2D (con agujeros) entre z0 y z1; to3(u, v, w) -> Vector en metros"""
    loops = [ccw(outline)] + [list(reversed(ccw(h))) for h in holes]
    flat = [p for l in loops for p in l]
    tris = tessellate_polygon([[(p.x, p.y, 0.0) for p in l] for l in loops])
    vb = [bm.verts.new(to3(p.x, p.y, z0)) for p in flat]; vt = [bm.verts.new(to3(p.x, p.y, z1)) for p in flat]
    for t in tris:
        try: bm.faces.new([vt[t[0]], vt[t[1]], vt[t[2]]]); bm.faces.new([vb[t[2]], vb[t[1]], vb[t[0]]])
        except ValueError: pass
    i0 = 0
    for l in loops:
        n = len(l)
        for k in range(n):
            a, b = i0 + k, i0 + (k + 1) % n
            bm.faces.new((vb[a], vb[b], vt[b], vt[a]))
        i0 += n
def box(bm, x0, x1, y0, y1, z0, z1):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(m(x1 - x0), m(y1 - y0), m(z1 - z0)))
    bmesh.ops.translate(bm, verts=g['verts'], vec=M((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
def cyl(bm, c, axis, r, L, seg=32, r2=None):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=m(r), radius2=m(r if r2 is None else r2), depth=m(L))
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector(axis)).to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=M(*c))

def mat(name, col):
    mt = bpy.data.materials.get(name)
    if mt: return mt
    mt = bpy.data.materials.new(name); mt.diffuse_color = (*col, 1); return mt
M_ACM = mat("Alucobond_Gris", (0.75, 0.77, 0.8)); M_AL = mat("Aluminio_Escuadras", (0.6, 0.62, 0.65))
M_PETG = mat("PETG_Negro_Soporte", (0.08, 0.08, 0.08))

col = bpy.data.collections.get("ACM4_SoportePrincipal")
if not col:
    col = bpy.data.collections.new("ACM4_SoportePrincipal"); sc.collection.children.link(col)
for o in list(col.objects):
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)
def make(name, bm, mt):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.normal_update()
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mt)
    o = bpy.data.objects.new(name, me); col.objects.link(o); return o

# ------------------------------------------------------------------ servo: medidas (la base se pliega hasta su brida)
def islas_v(o):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); seen = set(); out = []
    for f in b.faces:
        if f in seen: continue
        st = [f]; comp = []; seen.add(f)
        while st:
            g_ = st.pop(); comp.append(g_)
            for e in g_.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
        out.append(list({v: None for g_ in comp for v in g_.verts}))
    res_ = [[Vector(v.co) * 1000 for v in vs] for vs in out]; b.free(); return res_
sv = O.get(SERVO)
if not sv: raise SystemExit(f"no se encontro el servo {SERVO}")
_cv = max(islas_v(sv), key=lambda vs: (max(p.x for p in vs) - min(p.x for p in vs)) * (max(p.y for p in vs) - min(p.y for p in vs)) * (max(p.z for p in vs) - min(p.z for p in vs)))   # cuerpo = la parte de mayor volumen
SVX0, SVX1 = min(p.x for p in _cv), max(p.x for p in _cv)
def _rango(eje):
    """extremos del cuerpo en y o z, sin protuberancias (salida del cable): un extremo cuyos vertices ocupan menos
    del 30 % del largo del servo (x) es una protuberancia y se toma el siguiente nivel"""
    vals = sorted({round(getattr(p, eje), 2) for p in _cv}); lo, hi = vals[0], vals[-1]
    def chico(v):
        xs = [p.x for p in _cv if abs(getattr(p, eje) - v) < 0.05]; return (max(xs) - min(xs)) < 0.3 * (SVX1 - SVX0)
    if len(vals) > 2 and chico(hi): hi = vals[-2]
    if len(vals) > 2 and chico(lo): lo = vals[1]
    return lo, hi
SVY0, SVY1 = _rango("y"); SVZ0, SVZ1 = _rango("z")
XFL = SVX0 + SV_BRIDA                    # cara exterior de la placa = apoyo de la brida
XW = XFL - T                             # cara interior (A) de la placa
YC, ZC = (SVY0 + SVY1) / 2, (SVZ0 + SVZ1) / 2
YA, YB = SVY0 - SV_HOLG, SVY1 + SV_HOLG                    # ventana (en y)
ZH = SVZ0 - SV_APOYO - T                                    # esquina interior del pliegue de la bandeja
BAND_LE = max(BAND_L, SVZ1 + SV_HOLG + R_TOOL - ZH - 2 * D - KERF)
ZOT = ZH + 2 * D + BAND_LE + KERF                           # borde superior de la ventana
BRIDA = [(YC + a * SV_AG_L / 2, ZC + b * SV_AG_W / 2) for a in (-1, 1) for b in (-1, 1)]
YW_BACK = YC - SV_AG_L / 2 - SV_RAN - SV_AG_D / 2 - SV_MARGEN
ZW_TOP = max(ZOT, ZC + SV_AG_W / 2 + SV_AG_D / 2) + SV_MARGEN
if YC + SV_AG_L / 2 + SV_RAN + SV_AG_D / 2 + 1.5 > YW_FRONT: rep["avisos"].append("servo: agujero delantero de la brida muy cerca del borde")
if XW - BAND_LE < XR_OUT + 0.5: rep["avisos"].append("servo: la bandeja llega a la oreja derecha")
def ranura(yc, zc, r_=SV_AG_D / 2, L=SV_RAN, n=12):
    pts = [Vector((yc + L + r_ * math.cos(-math.pi / 2 + math.pi * k / n), zc + r_ * math.sin(-math.pi / 2 + math.pi * k / n))) for k in range(n + 1)]
    pts += [Vector((yc - L + r_ * math.cos(math.pi / 2 + math.pi * k / n), zc + r_ * math.sin(math.pi / 2 + math.pi * k / n))) for k in range(n + 1)]
    return pts
BRIDA_HOLES = [ranura(y_, z_) for y_, z_ in BRIDA]           # en (y, z)
# placa del servo (y, z), cara interior; el borde inferior entre Y_IN y YW_FRONT es el pliegue con la base
PLACA = [Vector(p) for p in [(Y_IN, Z_TOP), (YW_FRONT, Z_TOP), (YW_FRONT, ZW_TOP), (YW_BACK, ZW_TOP), (YW_BACK, ZH - 6.0), (Y_IN, Z_TOP + 12.0)]]
rep["servo"] = {"cuerpo_mm": [[round(SVX0, 1), round(SVX1, 1)], [round(SVY0, 1), round(SVY1, 1)], [round(SVZ0, 1), round(SVZ1, 1)]],
                "placa_x": [round(XW, 2), round(XFL, 2)], "placa_y": [round(YW_BACK, 1), YW_FRONT], "placa_z_tope": round(ZW_TOP, 1),
                "bandeja": {"x": [round(XW - BAND_LE, 1), round(XW, 1)], "y": [round(YA + KERF, 1), round(YB - KERF, 1)],
                            "z_sup": round(ZH + T, 2), "largo": round(BAND_LE, 1)}}

# ------------------------------------------------------------------ 2D: base, respaldo, orejas
BASE = [Vector(p) for p in [(60.75, -55.41), (32.28, 24.01), (XL_OUT, 24.01), (XL_OUT, Y_IN), (XR_IN, Y_IN), (XW, Y_IN),
                            (XW, Y_BASE_STEP), (60.75, Y_BASE_STEP)]]
BASE_HOLES = [circle(-0.01, -12.79, 12.69, 64), dogbone_rect(-22.38, -86.96, 34.85, -55.41),
              circle(43.58, -75.12, R_M3, 24), circle(53.63, -75.12, R_M3, 24)]
# respaldo (x, z) visto desde adelante, cara interior
RESP = [Vector(p) for p in [(XL_IN, Z_TOP), (XR_IN, Z_TOP), (XR_IN, Z_EAR), (13.53, 173.44), (13.53, 123.94),
                            (-13.54, 123.94), (-13.54, 173.44), (XL_IN, Z_EAR)]]
# agujeros de herrajes
EQ = {}
for s, xin in ((-1, XL_IN), (1, XR_IN)):
    sx = -s                         # hacia el centro
    EQ[s] = dict(
        base=[(xin + sx * a, Y_IN + b) for a, b in EQ_HB],
        resp=[(xin + sx * a, Z_TOP + c) for a, c in EQ_HR],
        oreja=[(Y_IN + b, Z_TOP + c) for b, c in EQ_HO])
BASE_HOLES += [circle(*h, R_M3, 24) for s in (-1, 1) for h in EQ[s]["base"]]
RESP_HOLES = [circle(*h, R_M3, 24) for s in (-1, 1) for h in EQ[s]["resp"]]
OREJA = [Vector(p) for p in [(Y_OUT, Z_TOP), (Y_FRONT, Z_TOP), (Y_FRONT, Z_EAR), (Y_OUT, Z_EAR)]]       # (y, z)
OREJA_HOLES = [circle(EJE[0], EJE[1], EJE[2] / 2, 48)] + [circle(*h, R_M3, 24) for h in EQ[-1]["oreja"]]

# ------------------------------------------------------------------ 3D
bm = bmesh.new()
prism(bm, BASE, BASE_HOLES, Z_BOT, Z_TOP, lambda u, v, w: M(u, v, w))
# respaldo: perfil (x, z) extruido en y; baja hasta Z_BOT (esquina del pliegue)
resp3 = [Vector((p.x, Z_BOT if abs(p.y - Z_TOP) < 1e-6 else p.y)) for p in RESP]
prism(bm, resp3, RESP_HOLES, Y_OUT, Y_IN, lambda u, v, w: M(u, w, v))
# placa del servo: perfil (y, z) extruido en x (XW..XFL); baja hasta Z_BOT en el pliegue con la base
placa3 = [Vector((q.x, Z_BOT if abs(q.y - Z_TOP) < 1e-6 else q.y)) for q in PLACA]
VENT = [Vector((YA, ZH)), Vector((YB, ZH)), Vector((YB, ZOT)), Vector((YA, ZOT))]
prism(bm, placa3, [VENT] + BRIDA_HOLES, XW, XFL, lambda u, v, w: M(w, u, v))
# bandeja: la parte de la ventana plegada hacia adentro (cara A abajo); incluye la esquina del pliegue
box(bm, XW - BAND_LE, XFL, YA + KERF, YB - KERF, ZH, ZH + T)
o_base = make("ACM4_Base_Respaldo", bm, M_ACM)
orejas = {}
for s, x0, x1 in ((-1, XL_OUT, XL_IN), (1, XR_IN, XR_OUT)):
    bm = bmesh.new(); prism(bm, OREJA, OREJA_HOLES, x0, x1, lambda u, v, w: M(w, u, v))
    orejas[s] = make("ACM4_Oreja_" + ("Izq" if s < 0 else "Der"), bm, M_ACM)
# esquineros PETG: pie (caja con la esquina interior superior achaflanada) + columna en la esquina oreja-respaldo
for s, xin in ((-1, XL_IN), (1, XR_IN)):
    sx = -s
    loc = lambda a, b, c: M(xin + sx * a, Y_IN + b, Z_TOP + c)
    pts = [(0, 0, 0), (EQ_X, 0, 0), (0, EQ_Y, 0), (EQ_X, EQ_Y, 0), (0, 0, EQ_Z), (EQ_X, 0, EQ_Z), (0, EQ_Y, EQ_Z)]
    bm = bmesh.new(); vs = [bm.verts.new(loc(*p)) for p in pts]
    bmesh.ops.convex_hull(bm, input=vs); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    xa, xb = sorted((xin, xin + sx * EQ_COL[0])); box(bm, xa, xb, Y_IN, Y_IN + EQ_COL[1], Z_TOP, Z_TOP + EQ_COL[2])
    eo = make("PETG_Esquinero_" + ("Izq" if s < 0 else "Der"), bm, M_PETG)
    hb = bmesh.new()       # agujeros para insertos termicos
    for a, b in EQ_HB: cyl(hb, (xin + sx * a, Y_IN + b, Z_TOP + INS_L / 2 - 0.5), (0, 0, 1), INS_D / 2, INS_L + 1)
    for a, c in EQ_HR: cyl(hb, (xin + sx * a, Y_IN + INS_L / 2 - 0.5, Z_TOP + c), (0, 1, 0), INS_D / 2, INS_L + 1)
    for b, c in EQ_HO: cyl(hb, (xin + sx * (INS_L / 2 - 0.5), Y_IN + b, Z_TOP + c), (1, 0, 0), INS_D / 2, INS_L + 1)
    me = bpy.data.meshes.new("tmp_h"); hb.to_mesh(me); hb.free(); ho = bpy.data.objects.new("tmp_h", me); sc.collection.objects.link(ho)
    md = eo.modifiers.new("h", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = ho; md.solver = 'EXACT'; md.use_self = True   # une pie y columna
    with bpy.context.temp_override(object=eo, active_object=eo): bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(ho, do_unlink=True); bpy.data.meshes.remove(me)
    # buje PETG con pestana por dentro
    bm = bmesh.new()
    # vastago (dentro del ACM, entra 0.5 mm en la pestana) + pestana; se perfora con use_self (une ambos)
    cyl(bm, (xin + sx * (0.25 - T / 2), EJE[0], EJE[1]), (1, 0, 0), BUJE_OD / 2, T + 0.5, 48)
    # pestana en D: el lado plano queda a 0.3 mm del respaldo
    ycut = Y_IN + 0.3; dp = []
    for q in circle(EJE[0], EJE[1], BUJE_FL_D / 2, 64):
        q = Vector((max(q.x, ycut), q.y))
        if not dp or (q - dp[-1]).length > 1e-4: dp.append(q)
    if (dp[0] - dp[-1]).length < 1e-4: dp.pop()
    xa, xb = sorted((xin, xin + sx * BUJE_FL_T))
    prism(bm, dp, [], xa, xb, lambda u, v, w: M(w, u, v))
    bo = make("PETG_Buje_" + ("Izq" if s < 0 else "Der"), bm, M_PETG)
    hb = bmesh.new(); cyl(hb, (xin, EJE[0], EJE[1]), (1, 0, 0), BUJE_ID / 2, 3 * T, 32)
    me = bpy.data.meshes.new("tmp_h"); hb.to_mesh(me); hb.free(); ho = bpy.data.objects.new("tmp_h", me); sc.collection.objects.link(ho)
    md = bo.modifiers.new("h", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = ho; md.solver = 'EXACT'; md.use_self = True
    with bpy.context.temp_override(object=bo, active_object=bo): bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(ho, do_unlink=True); bpy.data.meshes.remove(me)

orig = O.get("Soporte principal2_0")
if orig: orig.hide_set(True); orig.hide_render = True

# ------------------------------------------------------------------ piezas vecinas que abrazaban el aluminio
# SoporteServoEmpujadorMediaLuna rodea el respaldo y la oreja derecha por fuera: se hace una copia con el hueco
# agrandado al ACM + 0.2 mm (el original queda oculto como respaldo)
HOLG = 0.2
ADAPTAR = {}      # SoporteServoEmpujadorMediaLuna ya no se adapta: lo reemplaza la placa del servo plegada desde la base
REEMPLAZADAS = ["SoporteServoEmpujadorMediaLuna"]
for nm_ in REEMPLAZADAS:
    if O.get(nm_): O[nm_].hide_set(True); O[nm_].hide_render = True
rep["adaptadas"] = {}
for nm, cajas in ADAPTAR.items():
    src = O.get(nm)
    if not src: continue
    nn = nm + "_ACM4"
    if O.get(nn):
        old = O[nn]; me_ = old.data; bpy.data.objects.remove(old, do_unlink=True)
        if me_.users == 0: bpy.data.meshes.remove(me_)
    cp = src.copy(); cp.data = src.data.copy(); cp.name = nn; cp.data.name = nn; col.objects.link(cp)
    cb = bmesh.new()
    for c_ in cajas: box(cb, *c_)
    me = bpy.data.meshes.new("tmp_c"); cb.to_mesh(me); cb.free(); co = bpy.data.objects.new("tmp_c", me); sc.collection.objects.link(co)
    md = cp.modifiers.new("c", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = co; md.solver = 'EXACT'; md.use_self = True
    with bpy.context.temp_override(object=cp, active_object=cp): bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(co, do_unlink=True); bpy.data.meshes.remove(me)
    src.hide_set(True); src.hide_render = True
    b_ = bmesh.new(); b_.from_mesh(cp.data)
    rep["adaptadas"][nn] = {"cerrada": all(e.is_manifold for e in b_.edges)}; b_.free()

# ------------------------------------------------------------------ choques con el resto de la maquina
def tree(o, shrink=0.0):
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); b.normal_update()
    if shrink:
        for v in b.verts: v.co -= v.normal * shrink
    t = BVHTree.FromBMesh(b); b.free(); return t
def bbox(o):
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]; return [min(w[k] for w in ws) for k in range(3)], [max(w[k] for w in ws) for k in range(3)]
nuevos = list(col.objects)
otros = [q for q in O if q.type == 'MESH' and q.visible_get() and q not in nuevos and q.name not in ("Soporte principal2_0",) + tuple(ADAPTAR) + tuple(REEMPLAZADAS)]
nuevos_acm = [q for q in nuevos if not q.name.endswith("_ACM4")]
choques = {}
for n_ in nuevos_acm:
    a0, a1 = bbox(n_); tn = tree(n_, 0.0001)
    for q in otros:
        b0, b1 = bbox(q)
        if not all(b0[k] < a1[k] and b1[k] > a0[k] for k in range(3)): continue
        if tn.overlap(tree(q)): choques.setdefault(n_.name, []).append(q.name)
# entre piezas nuevas (deben tocarse sin penetrar)
for i, a in enumerate(nuevos):
    ta = tree(a, 0.0001)
    for b in nuevos[i + 1:]:
        if a.name.endswith("_ACM4") and b.name.endswith("_ACM4"): continue
        if ta.overlap(tree(b, 0.0001)): choques.setdefault(a.name, []).append(b.name)
# lo que ya chocaba con el soporte original (para no reportarlo como nuevo)
previos = []
if orig:
    to = tree(orig, 0.0001)
    for q in otros:
        b0, b1 = bbox(q); a0, a1 = bbox(orig)
        if all(b0[k] < a1[k] and b1[k] > a0[k] for k in range(3)) and to.overlap(tree(q)): previos.append(q.name)
rep["choques"] = choques; rep["choques_del_original"] = previos
# acceso: desde cada cabeza de tornillo, 15 mm hacia afuera sin tocar nada (incluida la copia adaptada del soporte del servo)
vecinos = list(otros) + [O[n_ + "_ACM4"] for n_ in ADAPTAR if O.get(n_ + "_ACM4")]
TV = {q.name: tree(q) for q in vecinos}
acceso = []
for s, xin, xout in ((-1, XL_IN, XL_OUT), (1, XR_IN, XR_OUT)):
    tiros = [(Vector((x, y, Z_BOT)), Vector((0, 0, -1)), "base") for x, y in EQ[s]["base"]]
    tiros += [(Vector((x, Y_OUT, z)), Vector((0, -1, 0)), "respaldo") for x, z in EQ[s]["resp"]]
    tiros += [(Vector((xout, y, z)), Vector((s, 0, 0)), "oreja") for y, z in EQ[s]["oreja"]]
    for p, d, cual in tiros:
        bloq = []
        u = d.orthogonal().normalized(); w = d.cross(u)
        for k in range(9):                       # eje + anillo de 3 mm de radio (cabeza y llave)
            off = Vector((0, 0, 0)) if k == 8 else (u * math.cos(2 * math.pi * k / 8) + w * math.sin(2 * math.pi * k / 8)) * 3.0
            org = M(*(p + off)) + d * 1e-5
            for nm_, tv in TV.items():
                if tv.ray_cast(org, d, 0.015)[0] is not None: bloq.append(nm_)
        acceso.append({"lado": "izq" if s < 0 else "der", "tornillo": cual, "en_mm": [round(c, 1) for c in p], "bloqueado_por": sorted(set(bloq))})
tiros = [(Vector((XFL, y_, z_)), Vector((1, 0, 0)), "brida servo (cabeza, afuera)") for y_, z_ in BRIDA]
tiros += [(Vector((XW, y_, z_)), Vector((-1, 0, 0)), "brida servo (tuerca, adentro)") for y_, z_ in BRIDA]
for p, d, cual in tiros:
    bloq = []
    u = d.orthogonal().normalized(); w = d.cross(u)
    for k in range(9):
        off = Vector((0, 0, 0)) if k == 8 else (u * math.cos(2 * math.pi * k / 8) + w * math.sin(2 * math.pi * k / 8)) * 3.0
        org = M(*(p + off)) + d * 1e-5
        for nm_, tv in TV.items():
            if nm_ == SERVO: continue                    # la brida queda fuera del cuerpo
            if tv.ray_cast(org, d, 0.012)[0] is not None: bloq.append(nm_)
    acceso.append({"lado": "der", "tornillo": cual, "en_mm": [round(c, 1) for c in p], "bloqueado_por": sorted(set(bloq))})
rep["acceso_tornillos"] = acceso

# ------------------------------------------------------------------ desarrollo plano (cara A arriba) y DXF
yf = lambda z: Y_IN - 2 * D - (z - Z_TOP)          # altura en el respaldo -> y del desarrollo
def resp_to_flat(p): return Vector((p.x, yf(p.y)))
outline = [Vector(p) for p in [(60.75, -55.41), (32.28, 24.01), (XL_OUT, 24.01), (XL_OUT, Y_IN), (XL_IN, Y_IN)]]
outline += [resp_to_flat(Vector(p)) for p in [(XL_IN, Z_EAR), (-13.54, 173.44), (-13.54, 123.94), (13.53, 123.94), (13.53, 173.44), (XR_IN, Z_EAR)]]
U0 = XW + 2 * D                                    # la placa del servo se despliega hacia +x desde el pliegue
def placa_to_flat(q): return Vector((U0 + q.y - Z_TOP, q.x))     # q = (y, z) -> (x, y) del desarrollo
outline += [Vector((XR_IN, Y_IN)), Vector((XW, Y_IN))]
outline += [placa_to_flat(q) for q in PLACA]
outline += [Vector((XW, YW_FRONT)), Vector((XW, Y_BASE_STEP)), Vector((60.75, Y_BASE_STEP))]
uh = U0 + ZH - Z_TOP; uf = uh + 2 * D + BAND_LE; ut = uf + KERF
CORTE_U = [Vector(p) for p in [(uh, YA), (ut, YA), (ut, YB), (uh, YB), (uh, YB - KERF), (uf, YB - KERF), (uf, YA + KERF), (uh, YA + KERF)]]
holes_flat = BASE_HOLES + [[resp_to_flat(p) for p in h] for h in RESP_HOLES] + [CORTE_U] + [[placa_to_flat(q) for q in h] for h in BRIDA_HOLES]
groove = (Vector((XL_IN, Y_IN - D)), Vector((XR_IN, Y_IN - D)))
groove_placa = (Vector((XW + D, Y_IN)), Vector((XW + D, YW_FRONT)))
groove_band = (Vector((uh + D, YA + KERF)), Vector((uh + D, YB - KERF)))

LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("RANURA_V", 5), ("TEXTO_NO_CORTAR", 3)]
def dxf(path, polys, lines_, texts):
    o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
    for nm, cl in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(cl), "6", "CONTINUOUS"]
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
COL = {"CORTE_EXTERIOR": "#111", "CORTE_INTERIOR": "#d22", "RANURA_V": "#1565c0", "TEXTO_NO_CORTAR": "#2e7d32"}
def svg_write(path, drawings):
    svg = []; yoff = 0.0; Wmax = 200.0
    for nm, dr in drawings.items():
        pts = [p for _, ps in dr["polys"] for p in ps] + [p for _, p, _, _ in dr["texts"]]
        x0 = min(p.x for p in pts); x1 = max(p.x for p in pts); y0 = min(p.y for p in pts); y1 = max(p.y for p in pts) + 5
        Y = lambda y, y1=y1: yoff + (y1 - y); X = lambda x, x0=x0: x - x0 + 10
        for lay, ps in dr["polys"]:
            svg.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="0.4"/>' % (
                " ".join("%.2f,%.2f" % (X(p.x), Y(p.y)) for p in ps), "#e9eef3" if lay == "CORTE_EXTERIOR" else "#fff", COL[lay]))
        for lay, a, b in dr["lines"]:
            svg.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.6" stroke-dasharray="%s"/>' % (
                X(a.x), Y(a.y), X(b.x), Y(b.y), COL[lay], "3,2" if lay == "RANURA_V" else "none"))
        for lay, p, h, t_ in dr["texts"]:
            svg.append('<text x="%.2f" y="%.2f" font-size="%.1f" font-family="sans-serif" fill="%s">%s</text>' % (X(p.x), Y(p.y), h, COL[lay], t_))
        yoff += (y1 - y0) + 15; Wmax = max(Wmax, x1 - x0 + 20)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" width="%.0fmm" height="%.0fmm"><rect width="100%%" height="100%%" fill="#fff"/>%s</svg>'
                 % (Wmax, yoff, Wmax, yoff, "".join(svg)))

def norm_origin(polys, lines_, texts):
    xs = [p.x for _, ps in polys for p in ps]; ys = [p.y for _, ps in polys for p in ps]
    o_ = Vector((min(xs), min(ys)))
    return ([(l, [p - o_ for p in ps]) for l, ps in polys], [(l, a - o_, b - o_) for l, a, b in lines_],
            [(l, p - o_, h, t) for l, p, h, t in texts], (max(xs) - min(xs), max(ys) - min(ys)))
drawings = {}
P = [("CORTE_EXTERIOR", outline)] + [("CORTE_INTERIOR", h) for h in holes_flat]
L = [("RANURA_V", groove[0], groove[1]), ("RANURA_V", groove_placa[0], groove_placa[1]), ("RANURA_V", groove_band[0], groove_band[1])]
top_y = max(p.y for p in outline)
Tx = [("TEXTO_NO_CORTAR", Vector((-20, Y_IN - D + 1.5)), 2.5, "PLIEGUE 90 deg - V CIERRA (respaldo hacia arriba)"),
      ("TEXTO_NO_CORTAR", Vector((XW + D + 1.0, YW_FRONT + 2.0)), 2.5, "PLIEGUE 90 deg - V CIERRA (placa del servo hacia arriba)"),
      ("TEXTO_NO_CORTAR", Vector((uh + D + 1.0, YB - KERF + 1.5)), 2.5, "PLIEGUE 90 deg - V CIERRA (bandeja hacia adentro)"),
      ("TEXTO_NO_CORTAR", Vector((XL_OUT, top_y + 15)), 4.0, "SOPORTE PRINCIPAL - BASE + RESPALDO + PLACA SERVO - ACM 4 mm - x1"),
      ("TEXTO_NO_CORTAR", Vector((XL_OUT, top_y + 9)), 3.0, "CARA ARRIBA EN CNC: A (interior: cara superior de la base). Ranura V por esta cara"),
      ("TEXTO_NO_CORTAR", Vector((XL_OUT, top_y + 4)), 3.0, "Ranura V 90 deg: dejar %.1f mm en el fondo. D3.4 = paso M3" % RESTO)]
drawings["Base_Respaldo"] = dict(zip(("polys", "lines", "texts", "size"), norm_origin(P, L, Tx)))
OP = [("CORTE_EXTERIOR", OREJA)] + [("CORTE_INTERIOR", h) for h in OREJA_HOLES]
OT = [("TEXTO_NO_CORTAR", Vector((Y_OUT, Z_EAR + 10)), 4.0, "OREJA - ACM 4 mm - x2 (iguales)"),
      ("TEXTO_NO_CORTAR", Vector((Y_OUT, Z_EAR + 4)), 3.0, "Borde izquierdo = atras (contra el respaldo)")]
drawings["Oreja"] = dict(zip(("polys", "lines", "texts", "size"), norm_origin(OP, [], OT)))
for f_ in os.listdir(OUT):
    if f_.startswith("SoportePrincipal_ACM4"): os.remove(os.path.join(OUT, f_))
for nm, dr in drawings.items():
    dxf(os.path.join(OUT, f"SoportePrincipal_ACM4_{nm}.dxf"), dr["polys"], dr["lines"], dr["texts"])
svg_write(os.path.join(OUT, "SoportePrincipal_ACM4_vista_previa.svg"), drawings)
rep["piezas_mm"] = {nm: [round(v, 1) for v in dr["size"]] for nm, dr in drawings.items()}

# verificacion del desarrollo: el respaldo plegado debe coincidir con el modelo 3D
rep["desarrollo"] = {"ranura_y": round(groove[0].y, 2), "ancho_ranura_cara_A": round(2 * D, 2),
                     "alto_respaldo_desarrollado": round(yf(Z_TOP) - yf(Z_EAR), 2), "alto_respaldo_3d": round(Z_EAR - Z_TOP, 2)}

with open(os.path.join(OUT, "SoportePrincipal_ACM4_herrajes.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"""SOPORTE PRINCIPAL (Ovum2_0) - ALUCOBOND 4 mm - HERRAJES Y ARMADO

Piezas ACM 4 mm (CNC, fresa 1/8"):
  Base_Respaldo x1  {rep['piezas_mm']['Base_Respaldo'][0]} x {rep['piezas_mm']['Base_Respaldo'][1]} mm  - 3 pliegues de 90 grados, todos con la ranura V por la
    cara A (dejar {RESTO} mm): respaldo, placa del servo (borde derecho de la base) y bandeja (corte en U de la ventana)
  Oreja x2          {rep['piezas_mm']['Oreja'][0]} x {rep['piezas_mm']['Oreja'][1]} mm  - planas, iguales

Impresas en PETG (stl/SoportePrincipal_ACM4/):
  Esquinero x2 (izq y der son espejo): pie {EQ_X:.0f} x {EQ_Y:.0f} x {EQ_Z:.0f} mm + columna {EQ_COL[0]:.0f} x {EQ_COL[1]:.0f} x {EQ_COL[2]:.0f} mm.
    Imprimir acostado sobre la cara que va contra el respaldo; 5 perimetros, 40 % relleno. 5 insertos termicos M3 c/u.
  Buje con pestana x2: OD {BUJE_OD} (entra en el agujero de {EJE[2]}), pestana D{BUJE_FL_D} x {BUJE_FL_T} por DENTRO, interior D{BUJE_ID}
    (ajustar el interior al eje real).

Herrajes:
  Insertos termicos M3 (D4 x 6): 10
  Tornillos M3 x 8 cabeza boton + arandela D7: 10
    por esquinero: 1 desde abajo (base), 2 desde atras (respaldo), 2 desde afuera (oreja)
  Servo: 4 tornillos M4 x 12 (o los del servo) + arandela + tuerca autofrenante, por las ranuras de la placa
    (cabeza del lado de la brida, afuera; tuerca por dentro, entre la oreja y la placa)
    (ranuras de +-{SV_RAN} mm: ajustan la posicion del eje del servo con el de la media luna)
  Sin remaches.

Armado:
  1) Plegar el respaldo (adhesivo estructural o epoxi en la ranura V y dejar curar).
  2) Calentar e introducir los 5 insertos en cada esquinero.
  3) Esquinero contra la base y el respaldo: 1 tornillo desde abajo + 2 desde atras.
  4) Oreja contra el esquinero y el extremo del respaldo: 2 tornillos desde afuera.
  5) Bujes: entrar desde adentro, pestana contra la cara interior de la oreja (pegar si queda flojo).
  (El paso 1 incluye los otros dos pliegues: placa del servo hacia arriba y bandeja hacia adentro; adhesivo en las ranuras.)
  6) Servo: entrarlo desde afuera, eje primero, por la ventana de la placa hasta apoyar la brida; el cuerpo descansa
     sobre la bandeja. Atornillar la brida; antes de apretar, alinear el eje del servo con el de la media luna (ranuras).
  CAPOTA: la placa del servo llega hasta y = {YW_BACK:.1f} (zona x {XW:.1f}..{XFL:.1f}, z {Z_TOP:.0f}..{ZW_TOP:.0f}).
  La Cubierta_Capota actual choca ahi; la capota nueva debe dejar la cara interior trasera en y <= {YW_BACK - 0.5:.1f}.
  NOTA: la brida es la de un servo estandar tipo MG996R (el modelo no la tiene). Medir el servo real y ajustar
  SV_BRIDA y SV_AG_* en el script antes de cortar (la placa, la bandeja y la base se recalculan solas).
  No apretar de mas: el nucleo del ACM se aplasta. Usar arandela ancha bajo cada cabeza.
""")

# ------------------------------------------------------------------ STL de las piezas impresas
def export(o, fp):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.wm.stl_export(filepath=fp, export_selected_objects=True, global_scale=1000.0)
for o in col.objects:
    if o.name.startswith("PETG_"): export(o, os.path.join(STL, o.name + ".stl"))
for f_ in os.listdir(STL):
    if f_.endswith("_ACM4.stl") and f_.startswith("SoporteServoEmpujadorMediaLuna"): os.remove(os.path.join(STL, f_))
rep["objetos"] = [o.name for o in col.objects]
if "save" in argv:
    bpy.ops.wm.save_mainfile(); rep["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(rep))
result = rep
