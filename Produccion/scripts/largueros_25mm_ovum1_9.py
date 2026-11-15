"""
Ovum1_9: largueros del bastidor de 20x20 a tubo cuadrado de 25x25 mm (pared 1.5 mm, con tapones).

El tubo crece hacia AFUERA y hacia ABAJO: la cara interior (donde llegan travesanos y escuadras) y la cara
superior (donde apoyan travesanos, escuadras y bandejas) no se mueven. Para no cambiar la altura de la
maquina, las patas de caucho pasan de 8 a 3 mm (almohadillas adhesivas).

Se modifica:
  - "Bastidor_Largueros_2020.003" (copia unida visible, coleccion Soportes_Mesa.001): se borran las caras
    de los 4 largueros y se agregan los tubos nuevos dentro del mismo objeto.
  - "Bastidor_Largueros_2020" y ".001" (piezas sueltas, coleccion oculta Soportes_Mesa): se reemplaza su malla.

Uso:  blender --background Ovum1_9.blend --python largueros_25mm_ovum1_9.py [-- save]
"""
import bpy, bmesh, json, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
O = bpy.data.objects
S_OLD, S_NEW, WALL = 0.020, 0.025, 0.0015
DZ = S_NEW - S_OLD          # lo que crece hacia abajo
EPS = 1e-4

def wbm(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); return bm

def largueros_from(o):
    """cajas de 20 mm de alto en z 0.0339..0.0539 con lado x de 20 mm (las piezas sueltas del objeto)"""
    bm = wbm(o); bm.verts.ensure_lookup_table(); seen = set(); out = []
    for v in bm.verts:
        if v.index in seen: continue
        st = [v]; comp = []; seen.add(v.index)
        while st:
            a = st.pop(); comp.append(a.co.copy())
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen: seen.add(b.index); st.append(b)
        out.append(comp)
    bm.free(); return out

def tube(bm, x_in, side, y0, y1, z0, mat_idx_alu, mat_idx_tap):
    """tubo 25x25 hueco: cara interior en x_in, crece hacia 'side' (+1/-1); con tapones de 8 mm"""
    xa, xb = sorted((x_in, x_in + side * S_NEW)); z1 = z0 + S_NEW
    def ring(x0_, x1_, z0_, z1_, y):
        return [bm.verts.new(c) for c in ((x0_, y, z0_), (x1_, y, z0_), (x1_, y, z1_), (x0_, y, z1_))]
    o0, o1 = ring(xa, xb, z0, z1, y0), ring(xa, xb, z0, z1, y1)
    i0 = ring(xa + WALL, xb - WALL, z0 + WALL, z1 - WALL, y0)
    i1 = ring(xa + WALL, xb - WALL, z0 + WALL, z1 - WALL, y1)
    fs = []
    for k in range(4):
        n = (k + 1) % 4
        fs.append(bm.faces.new((o0[k], o0[n], o1[n], o1[k])))          # pared exterior
        fs.append(bm.faces.new((i0[k], i1[k], i1[n], i0[n])))          # pared interior
        fs.append(bm.faces.new((o0[k], i0[k], i0[n], o0[n])))          # canto extremo y0
        fs.append(bm.faces.new((o1[k], o1[n], i1[n], i1[k])))          # canto extremo y1
    for f in fs: f.material_index = mat_idx_alu
    # tapones de plastico a ras en ambos extremos
    for ya, yb in ((y0, y0 + 0.008), (y1 - 0.008, y1)):
        g = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, verts=g['verts'], vec=(xb - xa - 2 * WALL - 0.0002, yb - ya, z1 - z0 - 2 * WALL - 0.0002))
        bmesh.ops.translate(bm, verts=g['verts'], vec=((xa + xb) / 2, (ya + yb) / 2, (z0 + z1) / 2))
        for f in {f for v in g['verts'] for f in v.link_faces}: f.material_index = mat_idx_tap
    return (xa, xb, y0, y1, z0, z1)

def mat_slot(o, name_prefix, fallback):
    for i, m in enumerate(o.data.materials):
        if m and m.name.startswith(name_prefix): return i
    m = bpy.data.materials.get(fallback)
    o.data.materials.append(m); return len(o.data.materials) - 1

report = {"tubos": {}, "avisos": []}

# ---------------------------------------------------------------- 1. piezas sueltas (coleccion oculta)
specs = []      # (x_in, side, y0, y1, z0)  en coordenadas de mundo
for nm in ("Bastidor_Largueros_2020", "Bastidor_Largueros_2020.001"):
    o = O[nm]; comps = largueros_from(o); new = []
    for c in comps:
        xs = [p.x for p in c]; ys = [p.y for p in c]; zs = [p.z for p in c]
        if abs((max(xs) - min(xs)) - S_OLD) > 1e-3 or abs((max(zs) - min(zs)) - S_OLD) > 1e-3:
            report["avisos"].append(f"{nm}: pieza que no es 20x20, se deja igual"); continue
        cx = (min(xs) + max(xs)) / 2; side = 1 if cx > 0 else -1
        x_in = min(xs) if side > 0 else max(xs)
        new.append((x_in, side, min(ys), max(ys), min(zs) - DZ))
    specs += new
    mw = o.matrix_world.copy(); bm = bmesh.new()
    ia = 0; it = mat_slot(o, "PETG_Negro", "PETG_Negro_Soporte")
    for s in new: tube(bm, s[0], s[1], s[2], s[3], s[4], ia, it)
    bm.transform(mw.inverted()); bm.to_mesh(o.data); o.data.update(); bm.free()
    report["tubos"][nm] = len(new)

P_ = O.get("Patas_Caucho")
if P_:
    zt = max((P_.matrix_world @ v.co).z for v in P_.data.vertices); mi = P_.matrix_world.inverted()
    for v in P_.data.vertices:
        w = P_.matrix_world @ v.co
        if abs(w.z - zt) < EPS: v.co = mi @ (w - Vector((0, 0, DZ)))
    P_.data.update()

# ---------------------------------------------------------------- 2. copia unida visible
J = O.get("Bastidor_Largueros_2020.003")
if J:
    mw = J.matrix_world.copy()
    bm = bmesh.new(); bm.from_mesh(J.data); bm.transform(mw)
    ip = mat_slot(J, "Caucho_Patas", "Caucho_Patas")
    # los 4 largueros de la copia unida: cajas 20x20 en z 0.0339..0.0539, de lado exterior en x = +-0.21 / +-0.0933
    cands = []
    for s in specs:
        x_out = s[0] + s[1] * S_OLD
        ys = [v.co.y for v in bm.verts if abs(v.co.x - x_out) < EPS and abs(v.co.z - (s[4] + DZ)) < EPS]
        if not ys: report["avisos"].append(f"copia unida: sin larguero en x={x_out:.4f}"); continue
        cands.append((s[0], s[1], min(ys), max(ys), s[4]))      # usa el largo propio de la copia
    # patas de caucho (componentes cilindricos de 8 mm) -> 3 mm, misma base sobre la mesa
    bm.verts.ensure_lookup_table(); seen = set(); nfeet = 0
    for v in bm.verts:
        if v.index in seen: continue
        st = [v]; comp = []; seen.add(v.index)
        while st:
            a_ = st.pop(); comp.append(a_)
            for e in a_.link_edges:
                b_ = e.other_vert(a_)
                if b_.index not in seen: seen.add(b_.index); st.append(b_)
        zs = [q.co.z for q in comp]
        if len(comp) >= 24 and abs((max(zs) - min(zs)) - 0.008) < 2e-4 and all(m_.material_index == ip for f_ in {f for q in comp for f in q.link_faces} for m_ in [f_]):
            zt = max(zs)
            for q in comp:
                if abs(q.co.z - zt) < EPS: q.co.z -= DZ
            nfeet += 1
    report["patas_copia_unida"] = nfeet
    kill = set()
    for x_in, side, y0, y1, z0 in cands:
        xa, xb = sorted((x_in, x_in + side * S_OLD))
        def inside(v): return (xa - EPS <= v.co.x <= xb + EPS and y0 - EPS <= v.co.y <= y1 + EPS and z0 + DZ - EPS <= v.co.z <= z0 + DZ + S_OLD + EPS)
        for f in bm.faces:
            if all(inside(v) for v in f.verts): kill.add(f)
    nk = len(kill)
    bmesh.ops.delete(bm, geom=list(kill), context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    ia = mat_slot(J, "Aluminio_2020", "Aluminio_2020"); it = mat_slot(J, "PETG_Negro", "PETG_Negro_Soporte")
    for c in cands: tube(bm, c[0], c[1], c[2], c[3], c[4], ia, it)
    bm.transform(mw.inverted()); bm.to_mesh(J.data); J.data.update(); bm.free()
    report["tubos"]["Bastidor_Largueros_2020.003"] = {"caras_borradas": nk, "largueros": [[round(v, 4) for v in c] for c in cands]}

# ---------------------------------------------------------------- 3. revision de interferencias (lo visible)
dg = bpy.context.evaluated_depsgraph_get(); vl = bpy.context.view_layer
def bvh(o):
    oe = o.evaluated_get(dg); me = oe.to_mesh(); b = bmesh.new(); b.from_mesh(me); oe.to_mesh_clear()
    b.transform(o.matrix_world); t = BVHTree.FromBMesh(b); b.free(); return t
if J:
    # solo la geometria nueva: tubos (caja exterior) contra el resto de objetos visibles
    tb = bmesh.new()
    for x_in, side, y0, y1, z0 in cands:
        xa, xb = sorted((x_in + side * 0.0003, x_in + side * S_NEW))
        g = bmesh.ops.create_cube(tb, size=1.0)
        bmesh.ops.scale(tb, verts=g['verts'], vec=(xb - xa, y1 - y0 - 0.0006, S_NEW - 0.0006))
        bmesh.ops.translate(tb, verts=g['verts'], vec=((xa + xb) / 2, (y0 + y1) / 2, z0 + S_NEW / 2))
    TT = BVHTree.FromBMesh(tb); tb.free()
    hits = []
    for o in vl.objects:
        if o.type != 'MESH' or o == J or not o.visible_get() or o.name.startswith("Huevo"): continue
        if TT.overlap(bvh(o)): hits.append(o.name)
    report["interferencias_tubos_nuevos"] = hits
    ws = [J.matrix_world @ v.co for v in J.data.vertices]
    report["bb_copia_unida"] = [[round(min(w[i] for w in ws), 4) for i in range(3)], [round(max(w[i] for w in ws), 4) for i in range(3)]]

if "save" in argv:
    bpy.ops.wm.save_mainfile(); report["guardado"] = bpy.data.filepath
print("RESULT " + json.dumps(report))
