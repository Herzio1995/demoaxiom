"""
Ovum2_2: BasePrincipal en plastico impreso (PETG), HUECA y rellenable con cemento (mortero fino / grout).
Reemplaza la solucion de ACM (aluminio compuesto) 4 mm + esquineros PETG + 10 tornillos M3.

Que hace
  1) Toma la geometria actual de la base (objeto BasePrincipal; si no existe, une ACM4_Base_Respaldo +
     ACM4_Oreja_Izq + ACM4_Oreja_Der). Guarda una copia oculta "BasePrincipal_ACM4_original" (es la que se usa
     como fuente si se vuelve a correr el script, asi el script es repetible).
  2) Engrosa la pieza SIN mover las caras que tocan otras piezas:
       - cara superior de la placa (z 60.95), cara delantera del respaldo (y -112.01) y caras interiores de las
         orejas (x -31.34 / 31.77) quedan fijas;
       - debajo de la placa crece un CAJON (quilla) hasta z 36.95, entre los postes traseros y el motor;
       - el respaldo crece hacia atras hasta y -128.01 y las orejas hacia afuera hasta x -48.2 / 48.2
         (gruesas solo debajo del agujero del eje: izq hasta z 116; der hasta z 105, porque mas arriba gira el
         acople del servo a 0.26 mm de la oreja). Alrededor del eje la oreja queda de 4 mm, como antes:
         izq Ø16.06 para el rodamiento, der Ø11.5 (lado del servo). Sin bujes.
  3) La quilla abraza los 2 postes traseros del bastidor (cajas de 25.8 x 25.8, 20 mm de alto): el cemento rodea
     los postes y toma la carga lateral.
  4) Cavidad interior continua (quilla + respaldo + orejas) con pared de WALL mm, nervios perforados que unen las
     dos pieles y hacen de anclaje (el cemento pasa por las ventanas y queda trabado), orificio de llenado y de
     venteo en el piso de la quilla.
  5) Insertos termicos de laton: M3 en el pedestal del soporte del pesador (donde iban los tornillos M3) y M4 en
     las paredes de los postes traseros (tornillo prisionero que traba la base al poste).
  6) Los esquineros PETG quedan integrados (macizos, sin tornillos) y se ocultan las piezas sueltas.
  7) Revisa choques contra el resto de la maquina (y los compara con los que ya tenia la base de ACM).

Uso:  blender --background Ovum2_2.blend --python base_principal_rellenable_ovum2_2.py -- [save] [render] [stl]
      (o dentro de Blender con exec(...): trabaja sobre el archivo abierto, sin guardar)
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.geometry import tessellate_polygon
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
BASE_DIR = os.path.dirname(bpy.data.filepath)
OUT = os.path.join(BASE_DIR, "renders", "BasePrincipal_Rellenable")
STL = os.path.join(BASE_DIR, "stl", "BasePrincipal_Rellenable")
rep = {"avisos": []}

# ------------------------------------------------------------------ parametros (mm, coordenadas de mundo)
NAME = "BasePrincipal"
SRC_NAME = "BasePrincipal_ACM4_original"
ACM_PARTS = ["ACM4_Base_Respaldo", "ACM4_Oreja_Izq", "ACM4_Oreja_Der"]
ESQUINEROS = ["PETG_Esquinero_Izq", "PETG_Esquinero_Der"]
WALL = 3.0                     # pared de plastico alrededor del cemento
Z_TOP = 60.95                  # cara superior de la placa (fija)
Z_PLATE_BOT = 56.95            # cara inferior de la placa ACM = tope de los postes
Z_KB = 36.95                   # piso de la quilla (cara de apoyo para imprimir)
Y_IN = -112.01                 # cara delantera del respaldo (fija)
# VARIANTE: "gruesa" (por defecto) = respaldo y orejas de 16 mm con cemento adentro;
#           "delgada" (argumento -- delgada) = respaldo y orejas de PETG macizo de 9 mm, cemento solo en el cajon
VARIANTE = "delgada" if "delgada" in argv else "gruesa"
T_MACIZO = 9.0
Y_BACK = -128.01 if VARIANTE == "gruesa" else -112.01 - T_MACIZO   # cara trasera del respaldo (capota en y -142)
XL_IN, XR_IN = -31.34, 31.77   # caras interiores de las orejas (fijas)
X_FAR = 48.2                   # cajon: abraza los postes traseros (paredes hasta x +-47.6)
X_EAR_L, X_EAR_R = ((-X_FAR, X_FAR) if VARIANTE == "gruesa" else (-31.34 - T_MACIZO, 31.77 + T_MACIZO))  # caras ext. de las orejas
Y_FRONT_EAR = -92.59           # borde delantero de las orejas
Z_THICK = 126.0                # alto de la zona gruesa del respaldo; arriba queda el ACM original
Z_THICK_L = 115.0              # oreja izquierda: gruesa hasta debajo del agujero del rodamiento (z 115.76)
Z_THICK_R = 105.0              # oreja derecha: gruesa solo hasta aca. Arriba gira el acople del servo (Cylinder.003),
                               # que pasa a 0.26 mm de la cara exterior del ACM (x 35.77): ahi la oreja queda como estaba
Z_NOTCH = 80.53                # fondo de la ranura central del respaldo (paso de la media luna)
X_NOTCH = (-13.54, 13.53)
EJE = (-105.47, 123.79, 11.5)  # agujero del eje en la oreja derecha (lado del servo), sin buje
D_ROD = 16.06                  # oreja izquierda (sin servo): agujero original para el RODAMIENTO, sin buje
BUJES = ["PETG_Buje_Izq", "PETG_Buje_Der"]   # ya no se usan: se ocultan
Y_KEEL_FRONT = -40.0           # la quilla termina aca (adelante esta el motor, y >= -33.8)
POSTES = [(-44.2, -19.2, -110.5, -85.5), (19.2, 44.2, -110.5, -85.5)]   # postes traseros 25x25 del bastidor
HOLG_POSTE = 0.4
EQ = dict(X=16.0, Y=16.0, Z=14.0, COL=(10.0, 11.0, 46.0))              # esquineros (ahora macizos e integrados)
# insertos termicos de laton (medidas tipo Ruthex): agujero, profundidad, diametro exterior y largo del inserto
INS = {"M3": dict(d=4.0, prof=6.5, od=4.6, L=5.7), "M4": dict(d=5.6, prof=9.0, od=6.3, L=8.1)}
Y_LOCK = -99.0; Z_LOCK = (Z_KB + Z_PLATE_BOT) / 2
INSERTOS = [   # (medida, uso, punto de entrada, direccion hacia adentro)
    ("M3", "Soporte HuevoPesador (pedestal, antes tornillo M3 pasante)", (43.58, -75.12, 72.99), (0, 0, -1)),
    ("M3", "Soporte HuevoPesador (pedestal, antes tornillo M3 pasante)", (53.63, -75.12, 72.99), (0, 0, -1)),
    ("M4", "Traba poste trasero izq (prisionero M4 contra el tubo)", (-54.2, Y_LOCK, Z_LOCK), (1, 0, 0)),
    ("M4", "Traba poste trasero der (prisionero M4 contra el tubo)", (54.36, Y_LOCK, Z_LOCK), (-1, 0, 0)),
]
FILL = (35.0, -52.0, 14.0)     # orificio de llenado en el piso de la quilla (x, y, diametro)
VENT = (-40.0, -121.0, 6.0) if VARIANTE == "gruesa" else (0.0, -112.0, 6.0)   # venteo, lejos del llenado
RIB_T = 2.4                    # espesor de nervios

m = lambda v: v / 1000.0
def M(x, y, z): return Vector((m(x), m(y), m(z)))

# ------------------------------------------------------------------ geometria auxiliar
def area2(p): return 0.5 * sum(p[i].x * p[(i + 1) % len(p)].y - p[(i + 1) % len(p)].x * p[i].y for i in range(len(p)))
def ccw(p): return p if area2(p) > 0 else list(reversed(p))
def offset(poly, d):
    """desplaza un poligono antihorario d mm hacia adentro (inglete en cada vertice)"""
    out = []; n = len(poly)
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1 = (p1 - p0).normalized(); e2 = (p2 - p1).normalized()
        a = p1 + Vector((-e1.y, e1.x)) * d; b = p1 + Vector((-e2.y, e2.x)) * d
        den = e1.x * e2.y - e1.y * e2.x
        if abs(den) < 1e-9: out.append(a); continue
        t = ((b.x - a.x) * e2.y - (b.y - a.y) * e2.x) / den
        out.append(a + e1 * t)
    return out
def prism(bm, outline, z0, z1):
    l = ccw(outline); tris = tessellate_polygon([[(p.x, p.y, 0.0) for p in l]])
    vb = [bm.verts.new(M(p.x, p.y, z0)) for p in l]; vt = [bm.verts.new(M(p.x, p.y, z1)) for p in l]
    for t in tris:
        bm.faces.new([vt[t[0]], vt[t[1]], vt[t[2]]]); bm.faces.new([vb[t[2]], vb[t[1]], vb[t[0]]])
    n = len(l)
    for k in range(n): bm.faces.new((vb[k], vb[(k + 1) % n], vt[(k + 1) % n], vt[k]))
def box(bm, x0, x1, y0, y1, z0, z1):
    g = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=g['verts'], vec=(m(x1 - x0), m(y1 - y0), m(z1 - z0)))
    bmesh.ops.translate(bm, verts=g['verts'], vec=M((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
def cyl(bm, c, axis, r, L, seg=32):
    g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=m(r), radius2=m(r), depth=m(L))
    bmesh.ops.rotate(bm, verts=g['verts'], cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(Vector(axis)).to_matrix())
    bmesh.ops.translate(bm, verts=g['verts'], vec=M(*c))
def mat(name, col):
    mt = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mt.diffuse_color = (*col, 1); return mt
M_PETG = mat("PETG_BasePrincipal", (0.16, 0.42, 0.62))
M_CEM = mat("Cemento_Relleno", (0.58, 0.57, 0.53))
M_LAT = mat("Laton_Insertos", (0.85, 0.63, 0.22))

# ------------------------------------------------------------------ temporales
TMP = bpy.data.collections.new("_tmp_base_rellenable"); sc.collection.children.link(TMP)
def tmp_obj(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); TMP.objects.link(o); o.hide_render = True; return o
def tmp_coll(name, objs):
    c = bpy.data.collections.new(name); TMP.children.link(c)
    for o in objs:
        for u in list(o.users_collection): u.objects.unlink(o)
        c.objects.link(o)
    return c
def boolean(obj, op, operand):
    md = obj.modifiers.new("b", 'BOOLEAN'); md.operation = op; md.solver = 'EXACT'; md.use_self = True
    if isinstance(operand, bpy.types.Collection): md.operand_type = 'COLLECTION'; md.collection = operand
    else: md.object = operand
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    obj.modifiers.remove(md); old = obj.data; obj.data = me
    if old.users == 0: bpy.data.meshes.remove(old)
def dbg(label, o):
    if "debug" not in argv: return
    bb_ = world_bm(o); nm_ = sum(1 for e in bb_.edges if not e.is_manifold); v_ = bb_.calc_volume(signed=True) * 1e6; bb_.free()
    print("DBG", label, o.name, "vol_cm3=%.1f" % v_, "nonmanifold=%d" % nm_)
def world_bm(o):
    dg = bpy.context.evaluated_depsgraph_get(); oe = o.evaluated_get(dg); me = oe.to_mesh()
    b = bmesh.new(); b.from_mesh(me); b.transform(o.matrix_world); oe.to_mesh_clear(); return b

# ------------------------------------------------------------------ 1) fuente (geometria ACM actual)
bp = O.get(NAME); src = O.get(SRC_NAME)
col = bpy.data.collections.get("ACM4_SoportePrincipal")
if bp: col = bp.users_collection[0]
if col is None:
    col = bpy.data.collections.new("ACM4_SoportePrincipal"); sc.collection.children.link(col)
if src is None:
    if bp is not None:
        src = bp.copy(); src.data = bp.data.copy(); rep["fuente"] = "BasePrincipal (copiado a %s)" % SRC_NAME
    else:
        parts = [O[n] for n in ACM_PARTS if O.get(n)]
        if not parts: raise SystemExit("no hay BasePrincipal ni piezas ACM4_* para usar como fuente")
        b = bmesh.new()
        for p_ in parts:
            pb = world_bm(p_); me_ = bpy.data.meshes.new("t"); pb.to_mesh(me_); pb.free(); b.from_mesh(me_); bpy.data.meshes.remove(me_)
        me = bpy.data.meshes.new(SRC_NAME); b.to_mesh(me); b.free()
        src = bpy.data.objects.new(SRC_NAME, me)
        for p_ in parts: p_.hide_set(True); p_.hide_render = True
        rep["fuente"] = "union de " + ", ".join(p_.name for p_ in parts)
    src.name = SRC_NAME; src.data.name = SRC_NAME; col.objects.link(src)
else:
    rep["fuente"] = SRC_NAME + " (corrida repetida)"
src.hide_set(True); src.hide_render = True
for n_ in ACM_PARTS + ESQUINEROS + BUJES:
    if O.get(n_): O[n_].hide_set(True); O[n_].hide_render = True

# ------------------------------------------------------------------ 2) volumen exterior (solido)
K = [Vector(p) for p in [(-X_FAR, Y_BACK), (X_FAR, Y_BACK), (X_FAR, Y_IN), (54.36, Y_IN), (54.36, -94.79), (66.53, -81.4),
                         (66.53, -55.41), (66.53 - (Y_KEEL_FRONT + 55.41) / 79.42 * 34.25, Y_KEEL_FRONT), (-35.34, Y_KEEL_FRONT),
                         (-35.34, -80.0), (-X_FAR, -80.0)]]
adds = []
b = bmesh.new(); prism(b, K, Z_KB, Z_TOP); adds.append(tmp_obj("add_quilla", b))
for nm, bx in [("resp_izq", (X_EAR_L, X_NOTCH[0], Y_BACK, Y_IN, Z_KB, Z_THICK)),
               ("resp_der", (X_NOTCH[1], XR_IN + 4.0, Y_BACK, Y_IN, Z_KB, Z_THICK)),
               ("resp_med", (X_NOTCH[0], X_NOTCH[1], Y_BACK, Y_IN, Z_KB, Z_NOTCH)),
               ("oreja_izq", (X_EAR_L, XL_IN, Y_BACK, Y_FRONT_EAR, Z_KB, Z_THICK_L)),
               ("oreja_der", (XR_IN, X_EAR_R, Y_BACK, Y_FRONT_EAR, Z_KB, Z_THICK_R)),
               ("boss_m4_izq", None)]:
    b = bmesh.new()
    if bx: box(b, *bx)
    else: cyl(b, (-51.0, Y_LOCK, Z_LOCK), (1, 0, 0), 6.0, 6.4)        # x -54.2 .. -47.8
    adds.append(tmp_obj("add_" + nm, b))
for s, xin in ((-1, XL_IN), (1, XR_IN)):     # esquineros macizos (pie achaflanado + columna)
    sx = -s; loc = lambda a, b_, c: M(xin + sx * a, Y_IN + b_, Z_TOP + c)
    # se meten 0.5 mm en la oreja, el respaldo y la placa: sin caras coplanares el boolean une limpio
    E_ = -0.5
    pts = [(E_, E_, E_), (EQ["X"], E_, E_), (E_, EQ["Y"], E_), (EQ["X"], EQ["Y"], E_), (E_, E_, EQ["Z"]), (EQ["X"], E_, EQ["Z"]), (E_, EQ["Y"], EQ["Z"])]
    b = bmesh.new(); vs = [b.verts.new(loc(*p)) for p in pts]; bmesh.ops.convex_hull(b, input=vs)
    xa, xb = sorted((xin - sx * 0.5, xin + sx * EQ["COL"][0])); box(b, xa, xb, Y_IN - 0.5, Y_IN + EQ["COL"][1], Z_TOP - 0.5, Z_TOP + EQ["COL"][2])
    adds.append(tmp_obj("add_esq", b))   # dos cuerpos que se solapan: el boolean con use_self los une
def limpiar(b):
    """la malla ACM trae una cara inferior incompleta y una arista suelta: se cierran antes de las uniones"""
    bmesh.ops.remove_doubles(b, verts=b.verts, dist=1e-6)
    bmesh.ops.delete(b, geom=[e for e in b.edges if e.is_wire], context='EDGES')
    bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_edges], context='VERTS')
    borde = [e for e in b.edges if e.is_boundary]
    if borde:
        r_ = bmesh.ops.holes_fill(b, edges=borde, sides=0)
        bmesh.ops.triangulate(b, faces=r_["faces"])
    rep["fuente_reparada_aristas"] = len(borde)
    return b
sol = tmp_obj("solido", limpiar(world_bm(src)))
dbg('fuente', sol)
boolean(sol, 'UNION', tmp_coll("c_adds", adds))
dbg('sol+adds', sol)

# ------------------------------------------------------------------ 3) cavidad (cemento)
cav_parts = []
b = bmesh.new(); prism(b, offset(ccw(K), WALL), Z_KB + WALL, Z_PLATE_BOT + 1.0); cav_parts.append(tmp_obj("cav_quilla", b))
if VARIANTE == "gruesa":           # cemento tambien en respaldo y orejas
    for nm, bx in [("resp_izq", (X_EAR_L + WALL, X_NOTCH[0] - WALL, Y_BACK + WALL, Y_IN - WALL, Z_KB + WALL, Z_THICK - WALL)),
                   ("resp_der", (X_NOTCH[1] + WALL, XR_IN + 1.0, Y_BACK + WALL, Y_IN - WALL, Z_KB + WALL, Z_THICK - WALL)),
                   ("resp_med", (X_NOTCH[0] - WALL, X_NOTCH[1] + WALL, Y_BACK + WALL, Y_IN - WALL, Z_KB + WALL, Z_NOTCH - WALL)),
                   ("oreja_izq", (X_EAR_L + WALL, XL_IN - WALL, Y_BACK + WALL, Y_FRONT_EAR - WALL, Z_KB + WALL, Z_THICK_L - WALL)),
                   ("oreja_der", (XR_IN + WALL, X_EAR_R - WALL, Y_BACK + WALL, Y_FRONT_EAR - WALL, Z_KB + WALL, Z_THICK_R - WALL))]:
        b = bmesh.new(); box(b, *bx); cav_parts.append(tmp_obj("cav_" + nm, b))
cav = cav_parts[0]
if len(cav_parts) > 1: boolean(cav, 'UNION', tmp_coll("c_cav", cav_parts[1:]))
dbg('cav union', cav)
# lo que debe quedar macizo: paredes de las cajas de los postes, bloque de la traba derecha, alrededor del eje
keep = []
for x0, x1, y0, y1 in POSTES:
    b = bmesh.new(); box(b, x0 - HOLG_POSTE - WALL, x1 + HOLG_POSTE + WALL, y0 - HOLG_POSTE - WALL, y1 + HOLG_POSTE + WALL, Z_KB - 1, Z_PLATE_BOT + WALL)
    keep.append(tmp_obj("keep_poste", b))
_, _, y0, y1 = POSTES[1]
b = bmesh.new(); box(b, 44.0, 56.0, y0 - HOLG_POSTE - WALL, y1 + HOLG_POSTE + WALL, Z_KB - 1, Z_TOP + 1); keep.append(tmp_obj("keep_traba_der", b))
b = bmesh.new(); cyl(b, (-45.0, EJE[0], EJE[1]), (1, 0, 0), D_ROD / 2 + WALL, 32); keep.append(tmp_obj("keep_eje_izq", b))
b = bmesh.new(); cyl(b, (45.0, EJE[0], EJE[1]), (1, 0, 0), EJE[2] / 2 + WALL, 32); keep.append(tmp_obj("keep_eje_der", b))
boolean(cav, 'DIFFERENCE', tmp_coll("c_keep", keep))
dbg('cav-keep', cav)
# nervios perforados: cajas que se restan de la cavidad + ventanas que se le devuelven (recortadas a la cavidad)
ribs, wins = [], bmesh.new()
def rib_h(axis, pos, t0, t1, pitch=12.0, w=6.0, h=5.0):
    """nervio de la quilla (vertical, ocupa toda la altura). axis 'x' = plano normal a x. Ventanas alternadas
    pegadas al piso y al techo: pasa el cemento y escapa el aire con la pieza en cualquier orientacion"""
    b = bmesh.new(); zc0, zc1 = Z_KB + WALL, Z_PLATE_BOT
    if axis == 'x': box(b, pos - RIB_T / 2, pos + RIB_T / 2, t0, t1, zc0 - 1, zc1 + 1)
    else: box(b, t0, t1, pos - RIB_T / 2, pos + RIB_T / 2, zc0 - 1, zc1 + 1)
    ribs.append(tmp_obj("rib", b))
    t = t0 + 3.0; k = 0
    while t + w < t1:
        za, zb = (zc0 - 2, zc0 + h) if k % 2 == 0 else (zc1 - h, zc1 + 2)
        if axis == 'x': box(wins, pos - RIB_T, pos + RIB_T, t, t + w, za, zb)
        else: box(wins, t, t + w, pos - RIB_T, pos + RIB_T, za, zb)
        t += pitch / 2; k += 1
def rib_v(axis, pos, c0, c1, z0, z1, pitch=16.0, h=8.0):
    """nervio de respaldo/oreja: une las dos pieles; ventanas centradas de 5 mm cada `pitch`, una al piso y una al techo"""
    b = bmesh.new()
    if axis == 'x': box(b, pos - RIB_T / 2, pos + RIB_T / 2, c0 - 1, c1 + 1, z0 - 1, z1 + 1)
    else: box(b, c0 - 1, c1 + 1, pos - RIB_T / 2, pos + RIB_T / 2, z0 - 1, z1 + 1)
    ribs.append(tmp_obj("rib", b))
    cm = (c0 + c1) / 2; zs = [z0 - 2]
    while zs[-1] + pitch < z1 - h: zs.append(zs[-1] + pitch)
    zs.append(z1 - h + 2)
    for z in zs:
        if axis == 'x': box(wins, pos - RIB_T, pos + RIB_T, cm - 2.5, cm + 2.5, z, z + h)
        else: box(wins, cm - 2.5, cm + 2.5, pos - RIB_T, pos + RIB_T, z, z + h)
yk0, yk1 = -82.1 + 0.0, Y_KEEL_FRONT - WALL
for xr in (-5.0, 22.0, 48.0): rib_h('x', xr, yk0 - 1, yk1 + 1)
rib_h('y', -62.5, -35.34 + WALL - 1, 66.53 - WALL + 1)
rib_h('y', -100.0, -15.8, 15.8)
if VARIANTE == "gruesa":           # nervios perforados que unen las dos pieles del respaldo y las orejas
    ycav = (Y_BACK + WALL, Y_IN - WALL)
    for xr in (-30.0, 30.0): rib_v('x', xr, *ycav, Z_KB + WALL, Z_THICK - WALL)
    rib_v('x', 0.0, *ycav, Z_KB + WALL, Z_NOTCH - WALL)
    rib_v('y', -106.0, X_EAR_L + WALL, XL_IN - WALL, Z_KB + WALL, Z_THICK_L - WALL)
    rib_v('y', -106.0, XR_IN + WALL, X_EAR_R - WALL, Z_KB + WALL, Z_THICK_R - WALL)
win = tmp_obj("ventanas", wins)
rib = ribs[0]
boolean(rib, 'UNION', tmp_coll("c_ribs", ribs[1:]))
boolean(rib, 'DIFFERENCE', win)          # nervios con sus ventanas (sin caras coplanares con la cavidad)
dbg('nervios', rib)
boolean(cav, 'DIFFERENCE', rib)
dbg('cav final', cav)

# ------------------------------------------------------------------ 4) restar: cavidad, cajas de postes, agujeros
subs = [cav]
for x0, x1, y0, y1 in POSTES:
    b = bmesh.new(); box(b, x0 - HOLG_POSTE, x1 + HOLG_POSTE, y0 - HOLG_POSTE, y1 + HOLG_POSTE, Z_KB - 5, Z_PLATE_BOT); subs.append(tmp_obj("caja_poste", b))
b = bmesh.new(); cyl(b, (-44.5, EJE[0], EJE[1]), (1, 0, 0), D_ROD / 2, 31.0, 64); subs.append(tmp_obj("rodamiento_izq", b))   # x -60 .. -29
b = bmesh.new(); cyl(b, (34.5, EJE[0], EJE[1]), (1, 0, 0), EJE[2] / 2, 11.0, 48); subs.append(tmp_obj("eje_der", b))           # x 29 .. 40
ins_rep = []
for med, uso, p, d in INSERTOS:
    sp = INS[med]; p = Vector(p); d = Vector(d)
    b = bmesh.new(); cyl(b, tuple(p + d * (sp["prof"] / 2 - 1.0)), tuple(d), sp["d"] / 2, sp["prof"] + 2.0, 24); subs.append(tmp_obj("ins", b))
    if med == "M4":                          # paso del prisionero hasta la caja del poste
        b = bmesh.new(); cyl(b, tuple(p + d * 10.0), tuple(d), 2.25, 16.0, 24); subs.append(tmp_obj("paso", b))
    ins_rep.append({"medida": med, "uso": uso, "entrada_mm": [round(c, 2) for c in p], "dir": list(d)})
for (x, y, dia), nm in ((FILL, "llenado"), (VENT, "venteo")):
    b = bmesh.new(); cyl(b, (x, y, Z_KB + WALL / 2), (0, 0, 1), dia / 2, WALL + 4.0, 32); subs.append(tmp_obj(nm, b))
boolean(sol, 'DIFFERENCE', tmp_coll("c_subs", subs))
dbg('sol final', sol)

def limpiar_final(o):
    """quita aristas degeneradas y cuerpos sueltos de volumen ~0 que dejan los booleanos"""
    b = bmesh.new(); b.from_mesh(o.data)
    bmesh.ops.remove_doubles(b, verts=b.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(b, edges=b.edges, dist=1e-6)
    seen = set(); quitar = []
    for f in b.faces:
        if f in seen: continue
        st = [f]; comp = []; seen.add(f)
        while st:
            g = st.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
        vol = abs(sum(g.calc_area() * g.normal.dot(g.calc_center_median()) for g in comp) / 3.0)
        if vol < 1e-9: quitar += comp            # < 1 mm3
    if quitar: bmesh.ops.delete(b, geom=quitar, context='FACES')
    bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_faces], context='VERTS')
    bmesh.ops.recalc_face_normals(b, faces=b.faces); b.to_mesh(o.data); b.free(); o.data.update()
    return len(quitar)
rep["caras_sueltas_quitadas"] = limpiar_final(sol) + limpiar_final(cav)
dbg('sol limpio', sol)

# ------------------------------------------------------------------ 5) objetos finales
def to_obj(name, tmp, mt, coll):
    me = tmp.data.copy(); me.name = name
    o = O.get(name)
    if o is None:
        o = bpy.data.objects.new(name, me); coll.objects.link(o)
    else:
        old = o.data; o.data = me
        if old.users == 0: bpy.data.meshes.remove(old)
    me.transform(o.matrix_world.inverted())          # el temporal esta en coordenadas de mundo
    me.materials.clear(); me.materials.append(mt); o.hide_set(False); o.hide_render = False
    me.polygons.foreach_set("use_smooth", [False] * len(me.polygons)); me.update()
    return o
base = to_obj(NAME, sol, M_PETG, col)
cem = to_obj(NAME + "_Cemento", cav, M_CEM, col)
# insertos visibles (cilindros de laton)
bi = bmesh.new()
for med, uso, p, d in INSERTOS:
    sp = INS[med]; p = Vector(p); d = Vector(d); cyl(bi, tuple(p + d * (sp["L"] / 2 + 0.1)), tuple(d), sp["od"] / 2, sp["L"], 24)
tmp_ins = tmp_obj("ins_vis", bi)
ins_o = to_obj(NAME + "_Insertos", tmp_ins, M_LAT, col)

# ------------------------------------------------------------------ limpieza de temporales
for o in list(TMP.all_objects):
    me = o.data; bpy.data.objects.remove(o, do_unlink=True)
    if me and me.users == 0: bpy.data.meshes.remove(me)
for c in list(TMP.children_recursive): bpy.data.collections.remove(c)
bpy.data.collections.remove(TMP)

# ------------------------------------------------------------------ 6) medidas
def stats(o):
    b = world_bm(o); vol = b.calc_volume(signed=True) * 1e6     # cm3
    seen = set(); isl = 0
    for f in b.faces:
        if f in seen: continue
        isl += 1; st = [f]; seen.add(f)
        while st:
            g = st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
    nm = sum(1 for e in b.edges if not e.is_manifold); b.free()
    return round(vol, 1), isl, nm
vb, ib, nb = stats(base); vc, ic, nc = stats(cem)
rep["base_petg"] = {"volumen_cm3": vb, "masa_g_maciza_PETG_1.27": round(vb * 1.27), "cuerpos": ib, "aristas_no_manifold": nb,
                    "pared_mm": WALL}
rep["cemento"] = {"volumen_cm3": vc, "litros": round(vc / 1000, 3), "masa_kg_mortero_2.1": round(vc * 2.1 / 1000, 2),
                  "volumenes_separados": ic, "aristas_no_manifold": nc}
if ic != 1: rep["avisos"].append(f"la cavidad tiene {ic} volumenes separados (deberia ser 1)")
rep["insertos"] = ins_rep
def bbox(o):
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [round(min(w[k] for w in ws) * 1000, 2) for k in range(3)], [round(max(w[k] for w in ws) * 1000, 2) for k in range(3)]
rep["bbox_mm"] = bbox(base)
rep["orificios"] = {"llenado": {"x": FILL[0], "y": FILL[1], "d": FILL[2]}, "venteo": {"x": VENT[0], "y": VENT[1], "d": VENT[2]},
                    "cara": "piso de la quilla, z %.2f" % Z_KB}

# ------------------------------------------------------------------ 7) choques
def tree(o, shrink=0.0):
    b = world_bm(o); bmesh.ops.triangulate(b, faces=b.faces); b.normal_update()   # triangulacion real (caras concavas)
    if shrink:
        for v in b.verts: v.co -= v.normal * m(shrink)
    t = BVHTree.FromBMesh(b); b.free(); return t
def toca(a, q, ta):
    a0, a1 = bbox(a); b0, b1 = bbox(q)
    if not all(b0[k] < a1[k] and b1[k] > a0[k] for k in range(3)): return False
    return ta.overlap(tree(q)) != []
propios = {NAME, NAME + "_Cemento", NAME + "_Insertos", SRC_NAME}
otros = [q for q in O if q.type == 'MESH' and q.visible_get() and q.name not in propios]
tb = tree(base, 0.05); ts = tree(src, 0.05)
nuevos = sorted(q.name for q in otros if toca(base, q, tb))
previos = sorted(q.name for q in otros if toca(src, q, ts))
rep["choques"] = {"base_nueva": nuevos, "base_ACM_anterior": previos,
                  "nuevos_por_el_cambio": sorted(set(nuevos) - set(previos))}
if rep["choques"]["nuevos_por_el_cambio"]: rep["avisos"].append("choques nuevos: " + ", ".join(rep["choques"]["nuevos_por_el_cambio"]))
# luz minima a los postes (deben quedar dentro de la caja sin tocar)
rep["postes_dentro_de_cajas_sin_tocar"] = "Bastidor_Largueros_2020.001" not in nuevos

print("REPORTE_BASE " + json.dumps(rep, ensure_ascii=False))
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "reporte.json"), "w", encoding="utf-8") as fh: json.dump(rep, fh, ensure_ascii=False, indent=1)

# ------------------------------------------------------------------ STL (mm)
def write_stl(o, path):
    b = world_bm(o); bmesh.ops.triangulate(b, faces=b.faces); b.normal_update()
    import struct
    with open(path, "wb") as fh:
        fh.write(b"BasePrincipal rellenable Ovum2_2".ljust(80, b" ")); fh.write(struct.pack("<I", len(b.faces)))
        for f in b.faces:
            fh.write(struct.pack("<3f", *f.normal))
            for v in f.verts: fh.write(struct.pack("<3f", *(v.co * 1000)))
            fh.write(b"\0\0")
    b.free()
if "stl" in argv:
    os.makedirs(STL, exist_ok=True)
    write_stl(base, os.path.join(STL, "BasePrincipal_PETG.stl")); write_stl(cem, os.path.join(STL, "BasePrincipal_Cemento_referencia.stl"))

if "save" in argv:
    bpy.ops.wm.save_mainfile(); print("GUARDADO", bpy.data.filepath)

# ------------------------------------------------------------------ renders (despues de guardar: nada de esto se guarda)
if "render" in argv:
    vis = [base, ins_o]
    for o in O:
        if o.name not in (NAME, NAME + "_Insertos"): o.hide_render = True
    r = sc.render; r.engine = 'BLENDER_WORKBENCH'; r.resolution_x, r.resolution_y = 1600, 1200; r.film_transparent = False
    sh = sc.display.shading; sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = True
    sh.cavity_type = 'BOTH'; sh.show_object_outline = True; sh.background_type = 'VIEWPORT'
    try: sh.background_color = (1, 1, 1)
    except Exception: pass
    if sc.world: sc.world.color = (1, 1, 1)
    cam_d = bpy.data.cameras.new("_cam_r"); cam = bpy.data.objects.new("_cam_r", cam_d); sc.collection.objects.link(cam)
    sc.camera = cam; cam_d.lens = 60
    tgt = Vector(((rep["bbox_mm"][0][0] + rep["bbox_mm"][1][0]) / 2000, (rep["bbox_mm"][0][1] + rep["bbox_mm"][1][1]) / 2000,
                  (rep["bbox_mm"][0][2] + rep["bbox_mm"][1][2]) / 2000))
    def shot(fname, direction, dist=0.52, objs=None):
        show = objs or vis
        for o in O:
            if o.type in ('MESH',): o.hide_render = o not in show
        d = Vector(direction).normalized(); cam.location = tgt + d * dist
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        r.filepath = os.path.join(OUT, fname); bpy.ops.render.render(write_still=True); print("RENDER", r.filepath)
    shot("01_iso_frente.png", (1.0, 1.3, 0.8))
    shot("02_iso_atras.png", (-1.1, -1.4, 0.7))
    shot("03_abajo_quilla.png", (0.7, 0.9, -1.0))
    # cortes: copias recortadas con una caja
    def corte(fname, caja, direction, dist=0.5):
        cuts = []
        for o in (base, cem, ins_o):
            c = o.copy(); c.data = o.data.copy(); c.name = "_corte_" + o.name; sc.collection.objects.link(c); cuts.append(c)
        bc = bmesh.new(); box(bc, *caja); cut = bpy.data.objects.new("_caja", bpy.data.meshes.new("_caja"))
        bc.to_mesh(cut.data); bc.free(); sc.collection.objects.link(cut); cut.hide_render = True
        for c in cuts:
            md = c.modifiers.new("c", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.solver = 'EXACT'; md.object = cut
        shot(fname, direction, dist, cuts)
        for c in cuts: bpy.data.objects.remove(c, do_unlink=True)
        bpy.data.objects.remove(cut, do_unlink=True)
    corte("04_corte_x-36_oreja_izq.png", (-100, -36, -200, 100, 0, 200), (-1.0, 0.35, 0.35))
    corte("05_corte_y-120_respaldo.png", (-100, 100, -120, 100, 0, 200), (0.35, 1.0, 0.35))
    corte("06_corte_x0_centro.png", (-100, 0, -200, 100, 0, 200), (-1.0, 0.3, 0.3))
    corte("08_corte_z47_planta.png", (-100, 100, -200, 100, Z_LOCK, 200), (0.15, 0.25, 1.0), 0.45)
    ctx = [q for q in O if q.type == 'MESH' and q.visible_get() and bbox(q)[0][0] < 120 and bbox(q)[1][0] > -120
           and bbox(q)[0][1] < 60 and bbox(q)[1][1] > -160 and bbox(q)[0][2] < 210 and q.name not in ("Cubierta_Capota", "Cubierta_Tapa_Acrilico", "Cubierta_Tapa_Tiradores", "Carcasa_Inferior", "Carcasa_Inferior_Rejilla")]
    shot("07_contexto_maquina.png", (1.0, -1.2, 0.8), 0.75, ctx + [base, ins_o])
