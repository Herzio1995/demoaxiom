"""
Ovum2_4_inox: CARCASA PROTECTORA del mecanismo (pesador + girador) con TAPA DE ACRILICO atornillada.

Concepto (estilo "cabina de tubos"): planchas PLANAS de inox 0.6 (corte a mano, sin dobleces) encajadas en ranuras
de un marco de "tubos" PETG de seccion redondeada (squircle 20 x 20). En cada esquina hay un NODO PETG con forma de
union de tubos (codo/T abombado) y en cada empalme nodo-tubo una BANDA gris claro (como las franjas de la referencia).

  - Caja trasera   x +-93, y -131 .. -36, z 43 .. 210 (ejes de los tubos = aristas de las planchas).
      Laterales y fondo cerrados; el fondo tiene una escotadura para la canaleta (x +-44, z >= 118) con RIBETE PETG.
      Frente: dos "jambas" (x 48..93) y el vano central abierto (x +-48) para el girador y la salida a las bocas.
  - Techo/visera   los tubos superiores siguen hasta y 38 (en voladizo) para cubrir el girador.
  - Tapa           acrilico 4 mm (x +-96, y -134..41) en un rebaje de 4 mm de los tubos superiores (queda al ras),
                   18 tornillos M3 a insertos termicos. Se ve todo el recorrido del huevo desde arriba.
  - Fijacion       4 patas M5 integradas en los tubos inferiores laterales a tuerca T del perfil 2020
                   (largueros x +-85.8 en y -124, travesano y -98).
  - Planchas       sujetas con tornillos M3 pasantes a traves del tubo (cabeza en cara exterior, tuerca embutida).

Salidas
  - Coleccion "Carcasa_Mecanismo" (PETG gris oscuro / bandas gris claro / inox / acrilico).
  - Produccion/stl/carcasa_mecanismo/*.stl  + Carcasa_lista.txt
  - Produccion/cnc/carcasa/*_INOX06_*.dxf (planchas) y Carcasa_Tapa_ACRIL4.dxf (laser o corte a mano)
  - Copia Ovum2_4_inox_antes_carcasa.blend (solo la primera vez)
Uso:  blender -b Ovum2_4_inox.blend --python Produccion/scripts/carcasa_mecanismo_ovum2_4.py -- [nosave]
Plantillas: python Produccion/scripts/plantillas_pvc.py Produccion/cnc/carcasa "*_INOX06_*.dxf" carta
"""
import bpy, bmesh, sys, os, math, json, shutil
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAVE = "nosave" not in argv
ROOT = os.path.dirname(bpy.data.filepath)
OUT_STL = os.path.join(ROOT, "Produccion", "stl", "carcasa_mecanismo")
OUT_CNC = os.path.join(ROOT, "Produccion", "cnc", "carcasa")
for d in (OUT_STL, OUT_CNC):
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.lower().endswith((".stl", ".dxf")): os.remove(os.path.join(d, f))
COL = "Carcasa_Mecanismo"
rep = {"avisos": []}
def aviso(s): rep["avisos"].append(s); print("AVISO:", s)

# ------------------------------------------------------------------ parametros (mm, mundo)
XS, XJ = 93.0, 48.0                 # plano lateral / borde del vano frontal
YB, YJ, YC = -131.0, -36.0, 38.0    # plano del fondo / plano de las jambas / borde delantero de la visera
ZB, ZT = 43.0, 210.0                # ejes de los tubos inferiores / superiores
ZJ = 74.0                           # borde inferior de las jambas (la placa BaseDelgadaMetal llega a x~58, z 61)
R = 10.0                            # medio lado del tubo (seccion squircle 20 x 20, |u|^4+|v|^4 = R^4)
R_NODO = R + 0.8                    # el nodo abomba un poco (aspecto de union fundida)
R_BANDA = R + 1.2; L_BANDA = 10.0
T_PL = 0.6                          # inox
RAN_W, RAN_FONDO = 1.2, 1.0         # ranura: ancho / termina a 1 mm del eje del tubo
PL_IN = 1.5                         # borde de la plancha a 1.5 mm del eje del tubo
T_ACR = 4.0; ACR_MARGEN = 3.0       # acrilico: espesor / cuanto pasa del eje de los tubos
Z_TOP = ZT + R                      # 220: cara superior de tubos y acrilico
REB_Z = Z_TOP - T_ACR - 0.2         # fondo del rebaje
NOTCH_X, NOTCH_Z = 44.0, 118.0      # escotadura de la canaleta en el fondo
M3_D, M3_CAB_D, M3_TUERCA_R = 3.4, 6.2, 3.35   # paso, cabeza (avellanado plano), tuerca 5.5 e/c (+holgura)
TOR_PROF = 6.0                      # los M3 pasan a 6 mm del eje (4.5 mm del borde de la plancha)
INS_D, INS_L = 4.0, 6.0             # inserto termico M3 para la tapa
M5_D, M5_CAB_D = 5.5, 10.0
X_LARGUERO = 85.8                   # eje de los largueros 2020 (x 73.3..98.3, hasta y -110.5, cara sup z 26.5)
Y_TRAVESANO = -98.0                 # eje del travesano 2020 (y -110.5..-85.5)
Z_PERFIL = 26.5
PATAS_Y = (-124.0, Y_TRAVESANO)

# ------------------------------------------------------------------ nodos y aristas
N = {}
for s, sx in (("L", -1), ("R", 1)):
    N["BB" + s] = Vector((sx * XS, YB, ZB)); N["FB" + s] = Vector((sx * XS, YJ, ZB))
    N["BT" + s] = Vector((sx * XS, YB, ZT)); N["FT" + s] = Vector((sx * XS, YJ, ZT))
    N["C" + s] = Vector((sx * XS, YC, ZT))
    N["FM" + s] = Vector((sx * XS, YJ, ZJ))
    N["JB" + s] = Vector((sx * XJ, YJ, ZJ)); N["JT" + s] = Vector((sx * XJ, YJ, ZT))

# paneles: normal (eje), coordenada del plano, signo exterior, ejes del plano (a, b), poligono (a, b), ranura (rects)
def rect(a0, a1, b0, b1): return [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
PANELES = {}
for s, sx in (("L", -1), ("R", 1)):
    PANELES["Lateral_" + ("Izq" if s == "L" else "Der")] = dict(
        n=0, c=sx * XS, ext=sx, ab=(1, 2),
        poly=rect(YB + PL_IN, YJ - PL_IN, ZB + PL_IN, ZT - PL_IN),
        slot=[(YB + RAN_FONDO, YJ - RAN_FONDO, ZB + RAN_FONDO, ZT - RAN_FONDO)])
    xa, xb = sorted((sx * (XJ + PL_IN), sx * (XS - PL_IN)))
    sa, sb = sorted((sx * (XJ + RAN_FONDO), sx * (XS - RAN_FONDO)))
    PANELES["Jamba_" + ("Izq" if s == "L" else "Der")] = dict(
        n=1, c=YJ, ext=1, ab=(0, 2), poly=rect(xa, xb, ZJ + PL_IN, ZT - PL_IN),
        slot=[(sa, sb, ZJ + RAN_FONDO, ZT - RAN_FONDO)])
XA = XS - PL_IN
PANELES["Fondo"] = dict(
    n=1, c=YB, ext=-1, ab=(0, 2),
    poly=[(-XA, ZB + PL_IN), (XA, ZB + PL_IN), (XA, ZT - PL_IN), (NOTCH_X, ZT - PL_IN), (NOTCH_X, NOTCH_Z),
          (-NOTCH_X, NOTCH_Z), (-NOTCH_X, ZT - PL_IN), (-XA, ZT - PL_IN)],
    slot=[(-XS + RAN_FONDO, XS - RAN_FONDO, ZB + RAN_FONDO, NOTCH_Z + 0.5),
          (-XS + RAN_FONDO, -NOTCH_X + 0.5, ZB + RAN_FONDO, ZT - RAN_FONDO),
          (NOTCH_X - 0.5, XS - RAN_FONDO, ZB + RAN_FONDO, ZT - RAN_FONDO)])

def lado(s): return "Izq" if s == "L" else "Der"
# (A, B, paneles, brazo A, brazo B)   brazo = largo de tubo que pertenece al nodo
ARISTAS = [("BBL", "BBR", ["Fondo"], 30, 30), ("BTL", "BTR", ["Fondo"], 30, 30), ("CL", "CR", [], 30, 30)]
for s in "LR":
    ARISTAS += [
        ("BB" + s, "FB" + s, ["Lateral_" + lado(s)], 19, 25),
        ("BB" + s, "BT" + s, ["Lateral_" + lado(s), "Fondo"], 30, 30),
        ("FB" + s, "FM" + s, ["Lateral_" + lado(s)], ZJ - ZB, 0),          # nodo inferior delantero + T de la jamba
        ("FM" + s, "FT" + s, ["Lateral_" + lado(s), "Jamba_" + lado(s)], 30, 30),
        ("BT" + s, "FT" + s, ["Lateral_" + lado(s)], 30, 30),
        ("FT" + s, "C" + s, [], (YC - YJ), 0),                     # visera: un solo nodo largo
        ("FM" + s, "JB" + s, ["Jamba_" + lado(s)], 22.5, 22.5),
        ("FT" + s, "JT" + s, ["Jamba_" + lado(s)], 22.5, 22.5),
        ("JB" + s, "JT" + s, ["Jamba_" + lado(s)], 30, 30)]
GRUPOS = [["BBL"], ["BBR"], ["FBL", "FML"], ["FBR", "FMR"], ["BTL"], ["BTR"], ["FTL", "CL"], ["FTR", "CR"],
          ["JBL"], ["JBR"], ["JTL"], ["JTR"]]
NOMBRE_NODO = {"BB": "Nodo_FondoInf", "FB": "Nodo_FrenteInf", "BT": "Nodo_FondoSup", "FT": "Nodo_Visera",
               "JB": "Nodo_VanoInf", "JT": "Nodo_VanoSup"}

# ------------------------------------------------------------------ primitivas (bmesh en mm)
def squircle(r, n=48):
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n; c, s = math.cos(t), math.sin(t)
        pts.append((r * math.copysign(abs(c) ** 0.5, c), r * math.copysign(abs(s) ** 0.5, s)))
    return pts
def eje_de(a, b):
    d = b - a; k = max(range(3), key=lambda i: abs(d[i])); return k
def otros(k): return [i for i in range(3) if i != k]
def sq_prism(bm, c0, c1, r):
    k = eje_de(c0, c1); u, v = otros(k); vs = []
    for c in (c0, c1):
        ring = []
        for a, b in squircle(r):
            p = Vector(c); p[u] += a; p[v] += b; ring.append(bm.verts.new(p))
        vs.append(ring)
    n = len(vs[0])
    bm.faces.new(vs[0][::-1]); bm.faces.new(vs[1])
    for i in range(n): bm.faces.new((vs[0][i], vs[0][(i + 1) % n], vs[1][(i + 1) % n], vs[1][i]))
def superelipsoide(bm, c, r):
    g = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
    for v in g["verts"]:
        d = v.co.copy(); s = (abs(d.x) ** 4 + abs(d.y) ** 4 + abs(d.z) ** 4) ** 0.25
        v.co = c + d / s * r
def box(bm, mn, mx):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g["verts"], vec=[mx[i] - mn[i] for i in range(3)])
    bmesh.ops.translate(bm, verts=g["verts"], vec=[(mx[i] + mn[i]) / 2 for i in range(3)])
def cyl(bm, c, ax, r, L, seg=24):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=L)
    bmesh.ops.rotate(bm, verts=g["verts"], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector(ax)).to_matrix())
    bmesh.ops.translate(bm, verts=g["verts"], vec=Vector(c))
def hexa(bm, c, ax, r, L): cyl(bm, c, ax, r, L, seg=6)
def recalc(bm): bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

# ------------------------------------------------------------------ objetos / booleanas
col = bpy.data.collections.get(COL)
if col is None:
    col = bpy.data.collections.new(COL); bpy.context.scene.collection.children.link(col)
for ob in list(col.objects): bpy.data.objects.remove(ob, do_unlink=True)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
tmp = bpy.data.collections.new("_tmp_carcasa"); bpy.context.scene.collection.children.link(tmp)

def bm_obj(name, bm, c=tmp):
    recalc(bm); me = bpy.data.meshes.new(name); bmesh.ops.scale(bm, verts=bm.verts, vec=(0.001,) * 3)
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new(name, me); c.objects.link(ob); return ob
def aplicar(ob, operand, op):
    m = ob.modifiers.new("b", "BOOLEAN"); m.operation = op; m.solver = "EXACT"; m.object = operand
    m.use_self = True; m.use_hole_tolerant = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear(); old = ob.data; ob.data = me; bpy.data.meshes.remove(old)
def borrar(ob): bpy.data.objects.remove(ob, do_unlink=True)
def bbox_mm(ob):
    vs = [ob.matrix_world @ v.co * 1000 for v in ob.data.vertices]
    return Vector([min(v[i] for v in vs) for i in range(3)]), Vector([max(v[i] for v in vs) for i in range(3)])

# ------------------------------------------------------------------ geometria derivada de las aristas
def arista_info(A, B):
    a, b = N[A], N[B]; k = eje_de(a, b); L = (b - a).length; d = (b - a) / L; return a, b, k, L, d
UNIONES = []          # (punto, eje k, aristas)  -> bandas
TUBOS = []            # (nombre, c0, c1, k, arista)
BRAZOS = {n: [] for n in N}
for A, B, pans, la, lb in ARISTAS:
    a, b, k, L, d = arista_info(A, B)
    if la > 0: BRAZOS[A].append((a, a + d * la))
    if lb > 0: BRAZOS[B].append((b, b - d * lb))
    if la + lb < L - 1e-6:
        TUBOS.append((a + d * la, b - d * lb, k, (A, B)))
        UNIONES += [(a + d * la, k), (b - d * lb, k)]
    elif 0 < la < L:
        UNIONES.append((a + d * la, k))

# tornillos M3 de las planchas: (punto en el eje del tornillo, eje normal (k), signo exterior, panel)
def dentro_poly(p, P):
    c = False; n = len(P)
    for i in range(n):
        x1, y1 = P[i]; x2, y2 = P[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1): c = not c
    return c
def dist_borde(p, P):
    best = 1e9
    for i in range(len(P)):
        a = Vector(P[i]); b = Vector(P[(i + 1) % len(P)]); q = Vector(p)
        t = max(0, min(1, (q - a).dot(b - a) / max((b - a).length_squared, 1e-9))); best = min(best, (a + (b - a) * t - q).length)
    return best
TORN = []
def posiciones(A, B, la, lb, L):
    """distancias desde A: 1 tornillo por brazo de nodo (fuera de la banda y del cruce) + n en el tubo recto"""
    out = []; lo = 13.5
    hi = la - L_BANDA / 2 - 3.5
    if la > 0 and hi >= lo: out.append((lo + hi) / 2)
    hi = lb - L_BANDA / 2 - 3.5
    if lb > 0 and hi >= lo: out.append(L - (lo + hi) / 2)
    if la + lb < L - 1e-6:
        r0, r1 = la + L_BANDA / 2 + 3.5, L - lb - L_BANDA / 2 - 3.5
        n = max(1, round((r1 - r0) / 60.0)) if r1 > r0 else 0
        out += [r0 + (r1 - r0) * (i + 0.5) / n for i in range(n)]
    return out
for A, B, pans, la, lb in ARISTAS:
    a, b, k, L, d = arista_info(A, B)
    for pn in pans:
        P = PANELES[pn]; nk = P["n"]; t = [i for i in range(3) if i not in (k, nk)][0]
        ia, ib = P["ab"]; cen = [sum(q[0] for q in P["poly"]) / len(P["poly"]), sum(q[1] for q in P["poly"]) / len(P["poly"])]
        cen3 = Vector(a); cen3[ia] = cen[0]; cen3[ib] = cen[1]
        sg = 1 if cen3[t] > a[t] else -1
        for s in posiciones(A, B, la, lb, L):
            p = a + d * s; p[t] += sg * TOR_PROF
            if any(abs(p.y - py) < 9 and abs(abs(p.x) - XS) < 1 and abs(p.z - ZB) < 12 for py in PATAS_Y): continue
            q2 = (p[ia], p[ib])
            if not dentro_poly(q2, P["poly"]) or dist_borde(q2, P["poly"]) < 3.9: continue
            TORN.append((p, nk, P["ext"], pn))
# ribete de la escotadura: sus tornillos tambien pasan por el fondo
RIB_T = 4.4; RIB_GRIP = 9.0; RIB_CAP = 2.0; RIB_ZTOP = ZT - R - 1.0
RIB_TORN = [(sx * (NOTCH_X + 4.5), z) for sx in (-1, 1) for z in (135.0, 165.0, 192.0)] + [(x, NOTCH_Z - 4.5) for x in (-30.0, 0.0, 30.0)]
for x, z in RIB_TORN: TORN.append((Vector((x, YB, z)), 1, -1, "Fondo_ribete"))

# insertos de la tapa (x, y)
IX = XS - 6.0
INSERTOS = [(sx * IX, y) for sx in (-1, 1) for y in (-126.0, -84.0, -42.0, 0.0, YC - 3.0)]
INSERTOS += [(x, YB + 5.0) for x in (-45.0, 0.0, 45.0)] + [(x, YC - 3.0) for x in (-45.0, 0.0, 45.0)]
INSERTOS += [(sx * 70.5, YJ + 5.0) for sx in (-1, 1)]
ACR = dict(x0=-(XS + ACR_MARGEN), x1=XS + ACR_MARGEN, y0=YB - ACR_MARGEN, y1=YC + ACR_MARGEN, r=4.0)

# ------------------------------------------------------------------ cortadores globales
def cortadores_bm(mn, mx, para_banda=False):
    """bmesh con todo lo que se resta a una pieza PETG cuyo bbox es mn..mx (mm)"""
    bm = bmesh.new(); M = 2.0
    def toca(lo, hi): return all(hi[i] > mn[i] - M and lo[i] < mx[i] + M for i in range(3))
    for nm, P in PANELES.items():
        for a0, a1, b0, b1 in P["slot"]:
            lo = [0, 0, 0]; hi = [0, 0, 0]; ia, ib = P["ab"]; nk = P["n"]
            lo[nk], hi[nk] = P["c"] - RAN_W / 2, P["c"] + RAN_W / 2
            lo[ia], hi[ia] = a0, a1; lo[ib], hi[ib] = b0, b1
            if toca(lo, hi): box(bm, lo, hi)
    # rebaje del acrilico (+ todo lo que queda arriba)
    lo = (ACR["x0"] - 0.4, ACR["y0"] - 0.4, REB_Z); hi = (ACR["x1"] + 0.4, ACR["y1"] + 0.4, Z_TOP + 20)
    if toca(lo, hi): box(bm, lo, hi)
    if para_banda: return bm
    for p, nk, ext, pn in TORN:
        if not toca([p[i] - 14 for i in range(3)], [p[i] + 14 for i in range(3)]): continue
        ax = [0, 0, 0]; ax[nk] = 1
        cyl(bm, p, ax, M3_D / 2, 40)
        if pn == "Fondo_ribete": continue
        pc = p.copy(); pc[nk] += ext * (7.0 + 10); cyl(bm, pc, ax, M3_CAB_D / 2, 20)      # cabeza, cara exterior
        pt = p.copy(); pt[nk] -= ext * (7.0 + 10); hexa(bm, pt, ax, M3_TUERCA_R, 20)       # tuerca, cara interior
    for x, y in INSERTOS:
        if toca((x - 3, y - 3, REB_Z - INS_L), (x + 3, y + 3, Z_TOP)): cyl(bm, (x, y, REB_Z - INS_L / 2 + 0.5), (0, 0, 1), INS_D / 2, INS_L + 1)
    for sx in (-1, 1):
        for py in PATAS_Y:
            x = sx * X_LARGUERO
            if toca((x - 6, py - 6, 20), (x + 6, py + 6, 60)):
                cyl(bm, (x, py, 20), (0, 0, 1), M5_D / 2, 30)
                cyl(bm, (x, py, Z_PERFIL + 0.2 + 6.0 + 20), (0, 0, 1), M5_CAB_D / 2, 40)
    return bm

def patas_bm(mn, mx):
    bm = bmesh.new(); n = 0
    for sx in (-1, 1):
        for py in PATAS_Y:
            lo = (sx * XS - 14 if sx > 0 else sx * XS - 10, py - 7, Z_PERFIL + 0.2)
            hi = (sx * XS + 10 if sx > 0 else sx * XS + 14, py + 7, ZB - R + 3)
            lo, hi = [min(lo[i], hi[i]) for i in range(3)], [max(lo[i], hi[i]) for i in range(3)]
            if all(hi[i] > mn[i] and lo[i] < mx[i] for i in range(3)) and mn.z < ZB - R + 0.5:
                box(bm, lo, hi); n += 1
    return bm, n

# ------------------------------------------------------------------ materiales
def mat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.diffuse_color = rgba
    try:
        if rgba[3] < 1: m.surface_render_method = "BLENDED"
    except Exception: pass
    return m
M_TUBO = mat("PETG_Gris_Oscuro", (0.10, 0.11, 0.12, 1.0))
M_BANDA = mat("PETG_Gris_Claro", (0.70, 0.71, 0.70, 1.0))
M_INOX = mat("Inox_Acero", (0.72, 0.75, 0.78, 1.0))
M_ACR = mat("Acrilico_Transparente", (0.75, 0.88, 0.95, 0.25))
def finalizar(ob, m):
    ob.data.materials.clear(); ob.data.materials.append(m); ob.color = m.diffuse_color
    tmp.objects.unlink(ob); col.objects.link(ob)

PIEZAS = []
def pieza_petg(nombre, pos_bm, cat, para_banda=False, quedarse_mayor=False):
    ob = bm_obj(nombre, pos_bm)
    mn, mx = bbox_mm(ob)
    pb, npat = patas_bm(mn, mx) if not para_banda else (None, 0)
    if npat:
        po = bm_obj(nombre + "_pat", pb); aplicar(ob, po, "UNION"); borrar(po)
    elif pb: pb.free()
    cb = cortadores_bm(mn, mx, para_banda)
    if para_banda:
        # hueco interior de la banda
        pass
    co = bm_obj(nombre + "_cut", cb); aplicar(ob, co, "DIFFERENCE"); borrar(co)
    if quedarse_mayor:
        bm = bmesh.new(); bm.from_mesh(ob.data); bm.verts.ensure_lookup_table()
        comps = []; seen = set()
        for v in bm.verts:
            if v.index in seen: continue
            st = [v]; seen.add(v.index); cc = []
            while st:
                x = st.pop(); cc.append(x)
                for e in x.link_edges:
                    y = e.other_vert(x)
                    if y.index not in seen: seen.add(y.index); st.append(y)
            comps.append(cc)
        if len(comps) > 1:
            def vol(cc):
                fs = {f for x in cc for f in x.link_faces}; return abs(sum(f.calc_area() * f.normal.dot(f.calc_center_median()) for f in fs) / 3)
            keep = max(comps, key=vol)
            bmesh.ops.delete(bm, geom=[x for cc in comps if cc is not keep for x in cc], context="VERTS")
            bm.to_mesh(ob.data)
        bm.free()
    finalizar(ob, M_BANDA if cat == "Banda" else M_TUBO)
    PIEZAS.append((ob, cat, npat)); return ob

# nodos
for grp in GRUPOS:
    bm = bmesh.new()
    for n in grp:
        superelipsoide(bm, N[n], R_NODO)
        for c0, c1 in BRAZOS[n]: sq_prism(bm, c0, c1, R)
    base = NOMBRE_NODO[grp[0][:2] if grp[0][:2] in NOMBRE_NODO else grp[0][:1]]
    pieza_petg(f"PETG_Carcasa_{base}_{lado(grp[0][-1])}", bm, "Nodo")
# tubos rectos
NOMBRE_TUBO = {("BB", "BB"): "Tubo_FondoInf", ("BT", "BT"): "Tubo_FondoSup", ("C", "C"): "Tubo_ViseraFrente",
               ("BB", "FB"): "Tubo_LateralInf", ("BB", "BT"): "Tubo_EsquinaFondo", ("FM", "FT"): "Tubo_EsquinaFrente",
               ("BT", "FT"): "Tubo_LateralSup", ("JB", "JT"): "Tubo_Vano"}
for c0, c1, k, (A, B) in TUBOS:
    key = (A.rstrip("LR"), B.rstrip("LR")); nm = NOMBRE_TUBO.get(key, f"Tubo_{A}_{B}")
    suf = "" if A[-1] != B[-1] else "_" + lado(A[-1])
    bm = bmesh.new(); sq_prism(bm, c0, c1, R)
    pieza_petg(f"PETG_Carcasa_{nm}{suf}", bm, "Tubo")
# bandas (anillo con ranuras; se queda el trozo exterior mas grande)
for i, (p, k) in enumerate(UNIONES):
    bm = bmesh.new(); ax = Vector((0, 0, 0)); ax[k] = 1
    sq_prism(bm, p - ax * L_BANDA / 2, p + ax * L_BANDA / 2, R_BANDA)
    ob = bm_obj(f"PETG_Carcasa_Banda_{i + 1:02d}", bm)
    hb = bmesh.new(); sq_prism(hb, p - ax * (L_BANDA / 2 + 1), p + ax * (L_BANDA / 2 + 1), R + 0.15)
    ho = bm_obj("_hueco", hb); aplicar(ob, ho, "DIFFERENCE"); borrar(ho)
    me = ob.data; bm2 = bmesh.new(); bm2.from_mesh(me); bmesh.ops.scale(bm2, verts=bm2.verts, vec=(1000,) * 3)
    tmp.objects.unlink(ob); bpy.data.objects.remove(ob);
    pieza_petg(f"PETG_Carcasa_Banda_{i + 1:02d}", bm2, "Banda", para_banda=True, quedarse_mayor=True)

# ribete de la escotadura (pieza plana en U)
bm = bmesh.new(); yb0, yb1 = YB - RIB_T / 2, YB + RIB_T / 2
for sx in (-1, 1):
    x0, x1 = sorted((sx * (NOTCH_X - RIB_CAP), sx * (NOTCH_X + RIB_GRIP)))
    box(bm, (x0, yb0, NOTCH_Z - RIB_GRIP), (x1, yb1, RIB_ZTOP))
box(bm, (-(NOTCH_X + RIB_GRIP), yb0, NOTCH_Z - RIB_GRIP), (NOTCH_X + RIB_GRIP, yb1, NOTCH_Z + RIB_CAP))
ob = bm_obj("PETG_Carcasa_Ribete_Canaleta", bm)
hb = bmesh.new(); box(hb, (-(NOTCH_X + RIB_GRIP) - 1, YB - RAN_W / 2, NOTCH_Z - RIB_GRIP - 1), (-NOTCH_X + 0.5, YB + RAN_W / 2, RIB_ZTOP + 1))
box(hb, (NOTCH_X - 0.5, YB - RAN_W / 2, NOTCH_Z - RIB_GRIP - 1), (NOTCH_X + RIB_GRIP + 1, YB + RAN_W / 2, RIB_ZTOP + 1))
box(hb, (-(NOTCH_X + RIB_GRIP) - 1, YB - RAN_W / 2, NOTCH_Z - RIB_GRIP - 1), (NOTCH_X + RIB_GRIP + 1, YB + RAN_W / 2, NOTCH_Z + 0.5))
for x, z in RIB_TORN: cyl(hb, (x, YB, z), (0, 1, 0), M3_D / 2, 20)
ho = bm_obj("_rib_cut", hb); aplicar(ob, ho, "DIFFERENCE"); borrar(ho)
finalizar(ob, M_TUBO); PIEZAS.append((ob, "Ribete", 0))

# ------------------------------------------------------------------ planchas de inox y tapa de acrilico
AGUJ = {nm: [] for nm in PANELES}
for p, nk, ext, pn in TORN:
    key = "Fondo" if pn == "Fondo_ribete" else pn
    P = PANELES[key]; AGUJ[key].append((p[P["ab"][0]], p[P["ab"][1]]))
PLANCHAS = []
def solido_plano(nombre, poly2, ab, nk, c0, c1, agujeros, r_ag, m):
    bm = bmesh.new(); ia, ib = ab
    def P3(a, b, n):
        v = [0, 0, 0]; v[ia] = a; v[ib] = b; v[nk] = n; return Vector(v)
    v0 = [bm.verts.new(P3(a, b, c0)) for a, b in poly2]; v1 = [bm.verts.new(P3(a, b, c1)) for a, b in poly2]
    n = len(poly2); bm.faces.new(v0[::-1]); bm.faces.new(v1)
    for i in range(n): bm.faces.new((v0[i], v0[(i + 1) % n], v1[(i + 1) % n], v1[i]))
    ob = bm_obj(nombre, bm)
    if agujeros:
        hb = bmesh.new(); ax = [0, 0, 0]; ax[nk] = 1
        for a, b in agujeros: cyl(hb, P3(a, b, (c0 + c1) / 2), ax, r_ag, 30, seg=20)
        ho = bm_obj("_ag", hb); aplicar(ob, ho, "DIFFERENCE"); borrar(ho)
    finalizar(ob, m); return ob
for nm, P in PANELES.items():
    ob = solido_plano(f"INOX_Carcasa_{nm}", P["poly"], P["ab"], P["n"], P["c"] - T_PL / 2, P["c"] + T_PL / 2, AGUJ[nm], M3_D / 2, M_INOX)
    PLANCHAS.append((ob, nm))
def rect_redondeado(x0, x1, y0, y1, r, n=8):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            t = math.radians(a0 + 90 * i / n); pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts
ACR_POLY = rect_redondeado(ACR["x0"], ACR["x1"], ACR["y0"], ACR["y1"], ACR["r"])
ob_acr = solido_plano("ACRILICO_Carcasa_Tapa", ACR_POLY, (0, 1), 2, Z_TOP - T_ACR, Z_TOP, INSERTOS, 3.4 / 2, M_ACR)

# ------------------------------------------------------------------ interferencias con la escena
def bvh_world(ob):
    dg = bpy.context.evaluated_depsgraph_get(); oe = ob.evaluated_get(dg); me = oe.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(ob.matrix_world); oe.to_mesh_clear()
    t = BVHTree.FromBMesh(bm); bm.free(); return t
otros_obj = [o for o in bpy.context.scene.objects if o.type == "MESH" and COL not in [c.name for c in o.users_collection]
             and "_tmp" not in "".join(c.name for c in o.users_collection) and o.visible_get() and not o.hide_render]
bv_otros = [(o, bvh_world(o)) for o in otros_obj]
nuevas = [p[0] for p in PIEZAS] + [p[0] for p in PLANCHAS] + [ob_acr]
choques = []
for ob in nuevas:
    t = bvh_world(ob)
    for o, to in bv_otros:
        if t.overlap(to): choques.append((ob.name, o.name))
rep["interferencias"] = choques
for a, b in choques: aviso(f"interferencia {a} <-> {b}")

# ------------------------------------------------------------------ STL + DXF + lista
def export_stl(ob, path):
    me = ob.data; tris = []
    me.calc_loop_triangles()
    W = ob.matrix_world
    with open(path, "wb") as fh:
        import struct
        fh.write(b"carcasa_mecanismo_ovum2_4".ljust(80, b" ")); fh.write(struct.pack("<I", len(me.loop_triangles)))
        for lt in me.loop_triangles:
            vs = [W @ me.vertices[i].co * 1000 for i in lt.vertices]
            nrm = (vs[1] - vs[0]).cross(vs[2] - vs[0]).normalized()
            fh.write(struct.pack("<3f", *nrm))
            for v in vs: fh.write(struct.pack("<3f", *v))
            fh.write(b"\0\0")
LAYERS = [("CORTE_EXTERIOR", 7), ("CORTE_INTERIOR", 1), ("DOBLEZ", 5), ("TEXTO_NO_CORTAR", 3)]
def dxf(path, polys, texts):
    o = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
         "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(LAYERS))]
    for nm, cl in LAYERS: o += ["0", "LAYER", "2", nm, "70", "0", "62", str(cl), "6", "CONTINUOUS"]
    o += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    f = lambda v: "%.4f" % v
    for lay, pts in polys:
        o += ["0", "POLYLINE", "8", lay, "66", "1", "70", "1", "10", "0", "20", "0", "30", "0"]
        for x, y in pts: o += ["0", "VERTEX", "8", lay, "10", f(x), "20", f(y), "30", "0"]
        o += ["0", "SEQEND", "8", lay]
    for lay, (x, y), h, txt in texts: o += ["0", "TEXT", "8", lay, "10", f(x), "20", f(y), "30", "0", "40", f(h), "1", txt]
    o += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o) + "\n")
def circ2(c, r, n=24): return [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
def dxf_pieza(path, poly, holes, r, rotulo, sub):
    x0 = min(p[0] for p in poly); y0 = min(p[1] for p in poly)
    T = lambda p: (p[0] - x0, p[1] - y0)
    W = max(p[0] for p in poly) - x0; H = max(p[1] for p in poly) - y0
    polys = [("CORTE_EXTERIOR", [T(p) for p in poly])] + [("CORTE_INTERIOR", circ2(T(h), r)) for h in holes]
    tx = [("TEXTO_NO_CORTAR", (W * 0.5 - 30, H * 0.5 + 6), 5.0, rotulo), ("TEXTO_NO_CORTAR", (W * 0.5 - 30, H * 0.5), 3.0, sub)]
    dxf(path, polys, tx); return W, H
lista = ["CARCASA DEL MECANISMO - Ovum2_4_inox  (carcasa_mecanismo_ovum2_4.py)", ""]
lista.append("PLANCHAS inox 0.6 (planas, sin dobleces; agujeros M3 = 3.4):")
for ob, nm in PLANCHAS:
    P = PANELES[nm]
    # vista desde fuera: espejar si el exterior mira al lado negativo del eje "a"
    poly = P["poly"]; holes = AGUJ[nm]
    W, H = dxf_pieza(os.path.join(OUT_CNC, f"Carcasa_{nm}_INOX06_desarrollo.dxf"), poly, holes, M3_D / 2,
                     f"Carcasa {nm} inox 0.6", "plana - sin dobleces")
    lista.append(f"  Carcasa_{nm}: {W:.1f} x {H:.1f} mm, {len(holes)} agujeros")
W, H = dxf_pieza(os.path.join(OUT_CNC, "Carcasa_Tapa_ACRIL4.dxf"), ACR_POLY, INSERTOS, 3.4 / 2, "Tapa acrilico 4 mm", "transparente")
lista += ["", f"TAPA acrilico 4 mm: {W:.1f} x {H:.1f} mm, esquinas R{ACR['r']:.0f}, {len(INSERTOS)} agujeros 3.4 (M3 x 10 cabeza boton + arandela)", ""]
lista.append("PETG (tubos/nodos gris oscuro, bandas gris claro):")
cats = {}
for ob, cat, npat in PIEZAS:
    export_stl(ob, os.path.join(OUT_STL, ob.name.replace("PETG_Carcasa_", "") + ".stl"))
    mn, mx = bbox_mm(ob); cats[cat] = cats.get(cat, 0) + 1
    lista.append(f"  {ob.name}: {mx.x - mn.x:.0f} x {mx.y - mn.y:.0f} x {mx.z - mn.z:.0f} mm" + (f"  ({npat} pata M5)" if npat else ""))
n_m3 = len([t for t in TORN if t[3] != "Fondo_ribete"]); n_rib = len(RIB_TORN)
lista += ["", "TORNILLERIA:",
          f"  {n_m3} x M3x16 cabeza plana/boton + tuerca M3 (planchas, pasan a traves del tubo)",
          f"  {n_rib} x M3x10 + tuerca (ribete de la canaleta)",
          f"  {len(INSERTOS)} x inserto termico M3 (D4 x 6) + M3x10 cabeza boton (tapa de acrilico)",
          f"  {2 * len(PATAS_Y)} x M5x12 + tuerca T de 2020 (patas)",
          "  Bandas: pegar con CA o cinta doble faz despues de armar (deslizan por el tubo antes de meter las planchas).",
          "", "ORDEN: tubos/nodos inferiores -> planchas en ranuras -> verticales -> superiores -> M3 -> patas M5 -> tapa."]
rep.update(piezas=cats, n_m3=n_m3, n_insertos=len(INSERTOS), n_choques=len(choques))
with open(os.path.join(OUT_STL, "Carcasa_lista.txt"), "w", encoding="utf-8") as fh: fh.write("\n".join(lista) + "\n")

bpy.data.collections.remove(tmp)
for me in list(bpy.data.meshes):
    if me.users == 0: bpy.data.meshes.remove(me)
print("INFORME", json.dumps(rep, ensure_ascii=False))
if SAVE:
    bak = os.path.join(ROOT, "Ovum2_4_inox_antes_carcasa.blend")
    if not os.path.exists(bak): shutil.copy2(bpy.data.filepath, bak)
    bpy.ops.wm.save_mainfile()
