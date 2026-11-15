"""
Ovum2_2 (archivo Ovum2_2_antes_base_rellenable.blend): BaseDelgada como PROTOTIPO macizo en PETG.

  1) Limpia la malla: une los 3 cuerpos (placa+respaldo y las 2 orejas), quita la arista suelta y cierra la cara
     abierta.
  2) Tapa los 10 agujeros de tornillo M3 que eran para los esquineros (2 en la placa, 4 en el respaldo, 2 por oreja).
     Quedan: el agujero central del motor, los del eje (izq Ø16.06 rodamiento, der Ø11.5) y los 2 del pedestal del
     soporte del pesador, que pasan a ser agujeros para inserto termico M3 (Ø4.0 x 6.5 desde arriba; abajo sigue
     el pasante Ø3.4).
  3) Cartelas (refuerzos) macizas e integradas:
       - en cada esquina oreja-placa-respaldo: el esquinero de antes (pie 16 x 16 x 14 mm achaflanado + columna
         10 x 11 x 46 mm), ya probado sin choques;
       - a lo largo del pie del respaldo, entre los dos esquineros: cartela triangular de 8 x 8 mm.
  3b) Bajo la placa: 4 nervios de PETG (8.4 x 14 mm) con una tira de ACM 4 x 12 mm EMBEBIDA en cada uno: 3
      longitudinales y 1 transversal, cruzados a media madera. Las tiras se meten con una PAUSA de impresion
      justo antes de la placa (sin tornillos). DXF de las tiras en cnc/alucobond.
  4) Encajes de 4.5 mm para la cabeza de los 4 postes del bastidor (la placa engrosada a z 52.44 se metia en ellos),
     con 0.4 mm de holgura: ademas centran la base al montarla. Se ocultan esquineros y bujes sueltos.
  5) Compara choques con la BaseDelgada original (que queda oculta como BaseDelgada_original).

Uso:  en Blender (Scripting > Open > Run Script)  o
      blender --background Ovum2_2_antes_base_rellenable.blend --python base_delgada_prototipo_ovum2_2.py -- [save] [stl]
"""
import bpy, bmesh, math, os, sys, struct
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects; sc = bpy.context.scene
NAME, ORIG = "BaseDelgada", "BaseDelgada_original"
m = lambda v: v / 1000.0
Z_TOP, Y_IN, XL_IN, XR_IN = 60.95, -112.01, -31.34, 31.77
R_M3 = 1.7
# agujeros de los esquineros que se tapan: (centro en el plano, eje)
TAPAR = [((-20.34, -101.01), 'z'), ((20.77, -101.01), 'z'),
         ((-26.34, 69.95), 'y'), ((-26.34, 88.95), 'y'), ((26.77, 69.95), 'y'), ((26.77, 88.95), 'y'),
         ((-99.01, 65.95), 'x'), ((-106.51, 78.95), 'x'),           # los de las orejas: x, en ambas orejas
         ((43.58, -75.12), 'z'), ((53.63, -75.12), 'z')]            # pedestal: el usuario lo dejo sin agujeros
PEDESTAL = []; Z_PED = 72.99         # sin insertos en el pedestal (antes: (43.58, -75.12), (53.63, -75.12))
# pedestal alargado por el usuario hasta x 66.09 (cara derecha vertical): base z 60.95, tapa z 72.99
PEDESTAL_NUEVO = [(33.84, -82.11, 60.95), (33.84, -68.75, 60.95), (66.09, -81.54, 60.95), (66.09, -69.33, 60.95),
                  (37.98, -80.25, 72.99), (37.98, -70.62, 72.99), (66.09, -80.25, 72.99), (66.09, -70.62, 72.99)]
INS_M3 = (4.0, 6.5)
EQ = dict(X=16.0, Y=16.0, Z=14.0, COL=(10.0, 11.0, 46.0))
CARTELA = 8.0
POSTES = [(-44.2, -19.2, -110.5, -85.5), (19.2, 44.2, -110.5, -85.5), (-46.6, -21.6, 1.5, 26.5), (21.6, 46.6, 1.5, 26.5)]
HOLG, Z_POSTE_TOPE = 0.4, 56.95       # tope de los postes: z 56.9
# tiras de ACM 4 x 12 mm EMBEBIDAS en nervios de PETG bajo la placa. La base se imprime apoyada en las puntas de
# los nervios; al llegar a la cara inferior de la placa se pausa, se meten las tiras en sus ranuras y la impresora
# cierra la placa por encima. Sin tornillos.
Z_PLACA_INF = 56.95
ACM_T, RIB_H = 4.0, 12.0              # tira de ACM (espesor, alto)
SLOT_W, SLOT_H = 4.4, 12.4            # ranura: 0.4 mm de holgura en espesor y en alto
NERV_W, NERV_H = 8.4, 14.0            # nervio de PETG bajo la placa: paredes de 2 mm, piso de 1.6 mm
NERV_END, SLOT_END = 2.0, 0.5         # pared en las puntas del nervio / holgura de la tira en cada punta
NOTCH_W = 4.2                         # ancho de las muescas a media madera en el ACM
Z_NERV = Z_PLACA_INF - NERV_H         # 42.95: puntas de los nervios (apoyo en la cama)
Z_SLOT = Z_PLACA_INF - SLOT_H         # 44.55: piso de la ranura
CON_ACM = False                       # 2026-11-05: sin tiras de aluminio -> nervios de PETG macizos (sin ranuras)
NERVIOS_ACM = [   # nombre, corre a lo largo de, posicion, desde, hasta (extremos del nervio de PETG)
    ("L_izq", 'y', -28.0, -84.0, -1.0),       # entre los postes izquierdos
    ("L_der", 'y', 36.0, -84.0, -1.0),        # entre los postes derechos
    ("L_centro", 'y', 0.0, -111.5, -38.0),    # del respaldo hasta antes del motor
    ("T", 'x', -60.0, -34.0, 64.0),           # transversal, a media placa
]
OCULTAR = ["PETG_Esquinero_Izq", "PETG_Esquinero_Der", "PETG_Buje_Izq", "PETG_Buje_Der"]   # integrados / sin bujes
rep = {}

src = O.get(ORIG)
if src is None:
    cur = O[NAME]; src = cur.copy(); src.data = cur.data.copy(); src.name = ORIG; src.data.name = ORIG
    for c in cur.users_collection: c.objects.link(src)
src.hide_set(True); src.hide_render = True
for n_ in OCULTAR:
    if O.get(n_): O[n_].hide_set(True); O[n_].hide_render = True
obj = O[NAME]

def tmp(name, b):
    bmesh.ops.recalc_face_normals(b, faces=b.faces)
    me = bpy.data.meshes.new(name); b.to_mesh(me); b.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o
def caja(b, x0, x1, y0, y1, z0, z1):
    g = bmesh.ops.create_cube(b, size=1.0)
    bmesh.ops.scale(b, verts=g['verts'], vec=(m(x1 - x0), m(y1 - y0), m(z1 - z0)))
    bmesh.ops.translate(b, verts=g['verts'], vec=(m((x0 + x1) / 2), m((y0 + y1) / 2), m((z0 + z1) / 2)))
def boolean(o, op, operand):
    md = o.modifiers.new("b", 'BOOLEAN'); md.operation = op; md.solver = 'EXACT'; md.object = operand; md.use_self = True
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    o.modifiers.remove(md); old = o.data; o.data = me
    if old.users == 0: bpy.data.meshes.remove(old)
def borrar(*objs):
    for o_ in objs:
        me_ = o_.data; bpy.data.objects.remove(o_, do_unlink=True)
        if me_.users == 0: bpy.data.meshes.remove(me_)
def medir(b):
    nm = sum(1 for e in b.edges if not e.is_manifold); seen = set(); isl = 0
    for f in b.faces:
        if f in seen: continue
        isl += 1; st = [f]; seen.add(f)
        while st:
            g = st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen: seen.add(h); st.append(h)
    return {"vol_cm3": round(b.calc_volume(signed=True) * 1e6, 1), "cuerpos": isl, "no_manifold": nm}

# 1) malla limpia en coordenadas de mundo
b = bmesh.new(); b.from_mesh(src.data); b.transform(src.matrix_world)
bmesh.ops.remove_doubles(b, verts=b.verts, dist=1e-6)
bmesh.ops.delete(b, geom=[e for e in b.edges if e.is_wire], context='EDGES')
bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_edges], context='VERTS')
rep["origen"] = medir(b)
# en la union placa-respaldo falta un triangulo de la cara trasera de la placa: se agrega (dos bordes abiertos que
# comparten un vertice y cuyos otros extremos ya estan unidos por una arista)
bd = [e for e in b.edges if e.is_boundary]; parches = 0
for i, e1 in enumerate(bd):
    for e2 in bd[i + 1:]:
        sh = set(e1.verts) & set(e2.verts)
        if len(sh) != 1: continue
        c = sh.pop(); a = e1.other_vert(c); d = e2.other_vert(c)
        if any(d in ed.verts for ed in a.link_edges):
            vs = list(e1.link_faces[0].verts); fwd = vs[(vs.index(a) + 1) % len(vs)] == c
            b.faces.new([c, a, d] if fwd else [a, c, d]); parches += 1
rep["triangulos_agregados"] = parches
# placa y respaldo se tocan por una arista con 4 caras: se separan en piezas cerradas
bmesh.ops.split_edges(b, edges=[e for e in b.edges if len(e.link_faces) > 2])
# 2) tapar agujeros: se borran las caras del tubo y se cierran las dos bocas
def dist_eje(p, c, ax):
    if ax == 'z': return math.hypot(p.x - c[0], p.y - c[1])
    if ax == 'y': return math.hypot(p.x - c[0], p.z - c[1])
    return math.hypot(p.y - c[0], p.z - c[1])
tubo = set()
for c, ax in TAPAR:
    A = Vector((ax == 'x', ax == 'y', ax == 'z'))
    for f in b.faces:
        if abs(f.normal.dot(A)) > 1e-3: continue
        if all(abs(dist_eje(v.co * 1000, c, ax) - R_M3) < 0.05 for v in f.verts): tubo.add(f)
rep["caras_de_agujeros_borradas"] = len(tubo)
bmesh.ops.delete(b, geom=list(tubo), context='FACES_ONLY')
bmesh.ops.delete(b, geom=[e for e in b.edges if not e.link_faces], context='EDGES')
borde = [e for e in b.edges if e.is_boundary]
if borde:
    r_ = bmesh.ops.holes_fill(b, edges=borde, sides=0); bmesh.ops.triangulate(b, faces=r_["faces"])
rep["bocas_cerradas"] = len(borde)
# separar en piezas (placa, respaldo, orejas) y unirlas con booleanos
seen = set(); piezas = []
for f in b.faces:
    if f in seen: continue
    st = [f]; comp = []; seen.add(f)
    while st:
        g = st.pop(); comp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h not in seen: seen.add(h); st.append(h)
    piezas.append(comp)
objs = []
for comp in sorted(piezas, key=len, reverse=True):
    pb = bmesh.new(); vm = {}
    for f in comp:
        for v in f.verts:
            if v not in vm: vm[v] = pb.verts.new(v.co)
        pb.faces.new([vm[v] for v in f.verts])
    objs.append(tmp("_pieza", pb))
b.free()
rep["piezas"] = len(objs)
base = objs[0]
for o_ in objs[1:]: boolean(base, 'UNION', o_)
borrar(*objs[1:])
# 3) cartelas
adds = []
for s, xin in ((-1, XL_IN), (1, XR_IN)):
    sx = -s; E_ = -0.5                        # se meten 0.5 mm en oreja, respaldo y placa
    loc = lambda a, b_, c: Vector((m(xin + sx * a), m(Y_IN + b_), m(Z_TOP + c)))
    pts = [(E_, E_, E_), (EQ["X"], E_, E_), (E_, EQ["Y"], E_), (EQ["X"], EQ["Y"], E_), (E_, E_, EQ["Z"]), (EQ["X"], E_, EQ["Z"]), (E_, EQ["Y"], EQ["Z"])]
    bb = bmesh.new(); vs = [bb.verts.new(loc(*p)) for p in pts]; bmesh.ops.convex_hull(bb, input=vs)
    bmesh.ops.delete(bb, geom=[v for v in bb.verts if not v.link_faces], context='VERTS')
    adds.append(tmp("_esq_pie", bb))
    bb = bmesh.new(); xa, xb = sorted((xin - sx * 0.5, xin + sx * EQ["COL"][0]))
    caja(bb, xa, xb, Y_IN - 0.5, Y_IN + EQ["COL"][1], Z_TOP - 0.5, Z_TOP + EQ["COL"][2]); adds.append(tmp("_esq_col", bb))
bb = bmesh.new()                              # cartela del pie del respaldo (prisma triangular a lo largo de x)
x0, x1 = XL_IN + EQ["X"] - 1.0, XR_IN - EQ["X"] + 1.0
tri = [(Y_IN - 0.5, Z_TOP - 0.5), (Y_IN + CARTELA, Z_TOP - 0.5), (Y_IN - 0.5, Z_TOP + CARTELA)]
v0 = [bb.verts.new((m(x0), m(y), m(z))) for y, z in tri]; v1 = [bb.verts.new((m(x1), m(y), m(z))) for y, z in tri]
bb.faces.new(v0); bb.faces.new(list(reversed(v1)))
for k in range(3): bb.faces.new((v0[k], v0[(k + 1) % 3], v1[(k + 1) % 3], v1[k]))
adds.append(tmp("_cartela_respaldo", bb))
# esquinas exteriores oreja-respaldo-placa: quedaba un hueco cubico de 4 x 4 x 4 mm (y ahi asomaba 0.5 mm el
# esquinero). Se rellena al ras de las caras exteriores y entrando 0.3 mm en las piezas vecinas
for xa, xb in ((XL_IN - 4.0, XL_IN + 0.3), (XR_IN - 0.3, XR_IN + 4.0)):
    bb = bmesh.new(); caja(bb, xa, xb, Y_IN - 4.0, Y_IN + 0.3, Z_TOP - 4.0, Z_TOP + 0.3); adds.append(tmp("_esquina", bb))
# franja inferior del respaldo (z 56.95..60.95): al separar placa y respaldo quedaba hueca; el usuario la relleno
bb = bmesh.new(); caja(bb, XL_IN - 4.0, XR_IN + 4.0, Y_IN - 4.0, Y_IN + 0.3, Z_TOP - 4.0, Z_TOP + 0.3); adds.append(tmp("_franja_respaldo", bb))
# retoque del usuario: pared sobre la placa (x -12.36..13.16, y -57.06..-53.56, hasta z 72.37)
bb = bmesh.new(); caja(bb, -12.36, 13.16, -65.78, -62.28, Z_TOP - 0.3, 72.37); adds.append(tmp("_pared_usuario", bb))
# pedestal nuevo: se quita el viejo al ras de la placa y se pone el alargado (antes quedaba una lamina de 0.05 mm
# que asomaba 0.5 mm por las esquinas del pedestal nuevo)
bb = bmesh.new(); caja(bb, 33.0, 67.5, -83.0, -67.5, Z_TOP, 80.0); _ped_viejo = tmp("_pedestal_viejo", bb)
boolean(base, 'DIFFERENCE', _ped_viejo); borrar(_ped_viejo)
bb = bmesh.new(); vs = [bb.verts.new(Vector((m(x), m(y), m(Z_TOP - 0.3 if z < 61 else z)))) for x, y, z in PEDESTAL_NUEVO]
bmesh.ops.convex_hull(bb, input=vs); bmesh.ops.delete(bb, geom=[v for v in bb.verts if not v.link_faces], context='VERTS')
adds.append(tmp("_pedestal_nuevo", bb))
def caja_eje(bb, eje, pos_a, pos_b, t0, t1, z0, z1):
    """caja con 'pos' perpendicular al nervio y 't' a lo largo"""
    if eje == 'y': caja(bb, pos_a, pos_b, t0, t1, z0, z1)
    else: caja(bb, t0, t1, pos_a, pos_b, z0, z1)
huecos = bmesh.new()      # ranuras cerradas para las tiras (quedan huecas por dentro hasta la pausa)
for nm_, eje, pos, a, bfin in NERVIOS_ACM:
    bb = bmesh.new(); caja_eje(bb, eje, pos - NERV_W / 2, pos + NERV_W / 2, a, bfin, Z_NERV, Z_PLACA_INF + 0.5); adds.append(tmp("_nervio", bb))
    if CON_ACM: caja_eje(huecos, eje, pos - SLOT_W / 2, pos + SLOT_W / 2, a + NERV_END, bfin - NERV_END, Z_SLOT, Z_PLACA_INF)
for a in adds: boolean(base, 'UNION', a)
if CON_ACM:
    hue = tmp("_ranuras", huecos); boolean(base, 'DIFFERENCE', hue); borrar(hue)
else: huecos.free()
# insertos M3 en el pedestal
bb = bmesh.new()
for x, y in PEDESTAL:
    g = bmesh.ops.create_cone(bb, cap_ends=True, segments=32, radius1=m(INS_M3[0] / 2), radius2=m(INS_M3[0] / 2), depth=m(INS_M3[1] + 2))
    bmesh.ops.translate(bb, verts=g['verts'], vec=(m(x), m(y), m(Z_PED - INS_M3[1] / 2 + 1)))
if PEDESTAL:
    ins = tmp("_ins", bb); boolean(base, 'DIFFERENCE', ins); borrar(ins)
else: bb.free()
borrar(*adds)
# encajes para los postes del bastidor: la placa engrosada (hasta z 52.44) se metia 4.5 mm en ellos
bb = bmesh.new()
for x0, x1, y0, y1 in POSTES: caja(bb, x0 - HOLG, x1 + HOLG, y0 - HOLG, y1 + HOLG, 40.0, Z_POSTE_TOPE)
enc = tmp("_encajes", bb); boolean(base, 'DIFFERENCE', enc); borrar(enc)
# limpieza final
b = bmesh.new(); b.from_mesh(base.data)
bmesh.ops.remove_doubles(b, verts=b.verts, dist=1e-6); bmesh.ops.dissolve_degenerate(b, edges=b.edges, dist=1e-6)
# astillas: trocitos de 1-2 triangulos de volumen ~0 encimados en la superficie (borde del agujero del rodamiento)
seen = set(); astillas = []
for f in b.faces:
    if f in seen: continue
    st = [f]; comp = []; seen.add(f)
    while st:
        g = st.pop(); comp.append(g)
        for e in g.edges:
            if len(e.link_faces) != 2: continue
            for h in e.link_faces:
                if h not in seen: seen.add(h); st.append(h)
    if len(comp) <= 10 and abs(sum(g.calc_area() * g.normal.dot(g.calc_center_median()) for g in comp)) < 1e-12: astillas += comp
if astillas: bmesh.ops.delete(b, geom=astillas, context='FACES')
bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_faces], context='VERTS')
borde = [e for e in b.edges if e.is_boundary]
if borde:
    r_ = bmesh.ops.holes_fill(b, edges=borde, sides=0); bmesh.ops.triangulate(b, faces=r_["faces"])
rep["astillas_quitadas"] = len(astillas)
# limpieza de topologia: vertices casi repetidos (< 0.25 mm), caras degeneradas, vertices sobrantes en caras planas
n0 = len(b.verts)
bmesh.ops.remove_doubles(b, verts=b.verts, dist=0.00025)
bmesh.ops.dissolve_degenerate(b, edges=b.edges, dist=1e-5)
import math as _m
bmesh.ops.dissolve_limit(b, angle_limit=_m.radians(0.5), use_dissolve_boundaries=False, verts=b.verts, edges=b.edges)
bmesh.ops.dissolve_degenerate(b, edges=b.edges, dist=1e-5)
bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_faces], context='VERTS')
# vertices que quedan en medio de una cara plana (contornos de encajes sin profundidad): se disuelven
b.normal_update()
for _ in range(3):
    sobran = [v for v in b.verts if len(v.link_faces) >= 2 and all(e.is_manifold for e in v.link_edges)
              and all(abs(f.normal.dot(v.link_faces[0].normal)) > 0.99999 for f in v.link_faces)]
    if not sobran: break
    bmesh.ops.dissolve_verts(b, verts=sobran); b.normal_update()
bmesh.ops.dissolve_degenerate(b, edges=b.edges, dist=1e-5)
bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_faces], context='VERTS')
rep["limpieza_vertices"] = [n0, len(b.verts)]
bmesh.ops.recalc_face_normals(b, faces=b.faces)
rep["resultado"] = medir(b)
b.transform(obj.matrix_world.inverted())
me = bpy.data.meshes.new(NAME); b.to_mesh(me); b.free()
mt = bpy.data.materials.get("PETG_BasePrincipal") or bpy.data.materials.new("PETG_BasePrincipal"); mt.diffuse_color = (0.16, 0.42, 0.62, 1)
me.materials.append(mt); me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
old = obj.data; obj.data = me
if old.users == 0: bpy.data.meshes.remove(old)
borrar(base)

# 3c) tiras de ACM (objetos aparte) con sus muescas a media madera, + DXF para cortarlas
from mathutils.geometry import tessellate_polygon
COL_N = bpy.data.collections.get("BaseDelgada_NerviosACM")
if COL_N is None:
    COL_N = bpy.data.collections.new("BaseDelgada_NerviosACM"); sc.collection.children.link(COL_N)
for o_ in list(COL_N.objects): borrar(o_)
for o_ in [x for x in O if x.name.startswith(("ACM_Tira_", "ACM_Nervio_"))]: borrar(o_)
M_ACM = bpy.data.materials.get("Alucobond_Gris") or bpy.data.materials.new("Alucobond_Gris")
T_ = [n for n in NERVIOS_ACM if n[1] == 'x'][0]
cruces = {}               # en el cruce: la transversal ocupa la mitad de abajo, la longitudinal la de arriba
for n in NERVIOS_ACM:
    if n[1] == 'y' and n[3] < T_[2] < n[4] and T_[3] < n[2] < T_[4]:
        cruces.setdefault(n[0], []).append(("abajo", T_[2])); cruces.setdefault(T_[0], []).append(("arriba", n[2]))
piezas_dxf = []
for nm_, eje, pos, a, bfin in (NERVIOS_ACM if CON_ACM else []):
    u0 = a + NERV_END + SLOT_END; L = (bfin - a) - 2 * NERV_END - 2 * SLOT_END; H = RIB_H; pts = [(0.0, 0.0)]
    mus = sorted([(c[1] - u0, c[0]) for c in cruces.get(nm_, [])])
    for u, lado in mus:
        if lado == "abajo": pts += [(u - NOTCH_W / 2, 0.0), (u - NOTCH_W / 2, H / 2), (u + NOTCH_W / 2, H / 2), (u + NOTCH_W / 2, 0.0)]
    pts += [(L, 0.0), (L, H)]
    for u, lado in reversed(mus):
        if lado == "arriba": pts += [(u + NOTCH_W / 2, H), (u + NOTCH_W / 2, H / 2), (u - NOTCH_W / 2, H / 2), (u - NOTCH_W / 2, H)]
    pts += [(0.0, H)]
    piezas_dxf.append((nm_, pts, [], L))
    bb = bmesh.new()
    def to3(u, v, w, pos=pos, u0=u0, eje=eje):
        z = Z_SLOT + v
        return Vector((m(pos + w), m(u0 + u), m(z))) if eje == 'y' else Vector((m(u0 + u), m(pos + w), m(z)))
    tris = tessellate_polygon([[(u, v, 0) for u, v in pts]])
    v0 = [bb.verts.new(to3(u, v, -ACM_T / 2)) for u, v in pts]; v1 = [bb.verts.new(to3(u, v, ACM_T / 2)) for u, v in pts]
    for t3 in tris:
        bb.faces.new([v0[t3[0]], v0[t3[1]], v0[t3[2]]]); bb.faces.new([v1[t3[2]], v1[t3[1]], v1[t3[0]]])
    for k in range(len(pts)): bb.faces.new((v0[k], v0[(k + 1) % len(pts)], v1[(k + 1) % len(pts)], v1[k]))
    bmesh.ops.recalc_face_normals(bb, faces=bb.faces)
    me_n = bpy.data.meshes.new("ACM_Tira_" + nm_); bb.to_mesh(me_n); bb.free(); me_n.materials.append(M_ACM)
    on = bpy.data.objects.new("ACM_Tira_" + nm_, me_n); COL_N.objects.link(on)
rep["tiras_acm"] = [{"pieza": n, "largo_mm": round(L, 1), "alto_mm": RIB_H, "muescas": len(cruces.get(n, []))} for n, p_, h, L in piezas_dxf]
if CON_ACM: rep["pausa_mm_desde_la_cama"] = round(Z_PLACA_INF - Z_NERV, 2)
else:
    rep["aluminio"] = "sin tiras: nervios de PETG macizos"
    if not COL_N.objects: bpy.data.collections.remove(COL_N); COL_N = None
def dxf_nervios(path):
    o_ = ["0", "SECTION", "2", "ENTITIES"]; f = lambda v: "%.3f" % v; yoff = 0.0
    for nm_, pts, hs, L in piezas_dxf:
        o_ += ["0", "POLYLINE", "8", "CORTE_EXTERIOR", "66", "1", "70", "1"]
        for u, v in pts: o_ += ["0", "VERTEX", "8", "CORTE_EXTERIOR", "10", f(u), "20", f(v + yoff)]
        o_ += ["0", "SEQEND"]
        for u, v in hs: o_ += ["0", "CIRCLE", "8", "CORTE_INTERIOR", "10", f(u), "20", f(v + yoff), "40", f(1.6)]
        o_ += ["0", "TEXT", "8", "TEXTO_NO_CORTAR", "10", f(2), "20", f(yoff + RIB_H + 2), "40", "2.5", "1",
               "Tira " + nm_ + " - ACM 4 mm - va embebida (muescas: ver orden de montaje)"]
        yoff += RIB_H + 12
    o_ += ["0", "ENDSEC", "0", "E" + "OF"]
    with open(path, "w", newline="\r\n") as fh: fh.write("\n".join(o_) + "\n")

# 4) choques: nuevos respecto de la original
def tree(o, s=0.0):
    dg = bpy.context.evaluated_depsgraph_get(); oe = o.evaluated_get(dg); me_ = oe.to_mesh()
    b_ = bmesh.new(); b_.from_mesh(me_); b_.transform(o.matrix_world); oe.to_mesh_clear()
    bmesh.ops.triangulate(b_, faces=b_.faces); b_.normal_update()
    for v in b_.verts: v.co -= v.normal * m(s)
    t = BVHTree.FromBMesh(b_); b_.free(); return t
nervios_obj = list(COL_N.objects) if COL_N else []
otros = [q for q in O if q.type == 'MESH' and q.visible_get() and q.name not in (NAME, ORIG) and q not in nervios_obj]
tn, to = tree(obj, 0.05), tree(src, 0.05)
nuevos = sorted(q.name for q in otros if tn.overlap(tree(q)))
previos = sorted(q.name for q in otros if to.overlap(tree(q)))
rep["choques"] = {"ahora": nuevos, "antes": previos, "nuevos": sorted(set(nuevos) - set(previos))}
rep["choques_tiras_acm"] = {n_.name: sorted(q.name for q in otros + [obj] if tree(n_, 0.05).overlap(tree(q))) for n_ in nervios_obj}
print("BASE_DELGADA", rep)

if "stl" in argv:
    D = os.path.join(os.path.dirname(bpy.data.filepath), "stl", "BaseDelgada_prototipo"); os.makedirs(D, exist_ok=True)
    b = bmesh.new(); b.from_mesh(obj.data); b.transform(obj.matrix_world)
    z0 = min(v.co.z for v in b.verts)
    for v in b.verts: v.co.z -= z0
    bmesh.ops.triangulate(b, faces=b.faces); b.normal_update()
    with open(os.path.join(D, "BaseDelgada_PETG.stl"), "wb") as fh:
        fh.write(b"BaseDelgada prototipo PETG".ljust(80, b" ")); fh.write(struct.pack("<I", len(b.faces)))
        for f in b.faces:
            fh.write(struct.pack("<3f", *f.normal))
            for v in f.verts: fh.write(struct.pack("<3f", *(v.co * 1000)))
            fh.write(b"\0\0")
    b.free(); print("STL", D)
    C = os.path.join(os.path.dirname(bpy.data.filepath), "cnc", "alucobond"); os.makedirs(C, exist_ok=True)
    if CON_ACM: dxf_nervios(os.path.join(C, "BaseDelgada_Nervios_ACM4.dxf")); print("DXF", C)
if "save" in argv: bpy.ops.wm.save_mainfile(); print("GUARDADO", bpy.data.filepath)
